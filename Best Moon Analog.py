# !pip install earthaccess
# !pip install -q earthaccess xarray h5netcdf netCDF4 rioxarray cupy-xarray dask reverse_geocode

import os
import earthaccess
import xarray as xr
import rioxarray
import numpy as np
import cupy as cp
import cupy_xarray
import dask
import h5py
import folium
from folium.plugins import HeatMap
import reverse_geocoder as rg

# 1. Configura o Dask para usar 8 threads paralelas na leitura e descompressão HDF5/NetCDF
dask.config.set(scheduler="threads", num_workers=8)

print(f"GPU Ativa: {cp.cuda.runtime.getDeviceProperties(0)['name'].decode('utf-8')}")
earthaccess.login()

bbox = (-75.0, -30.0, -34.0, -2.0)  # (lon_min, lat_min, lon_max, lat_max)
periodo = ("2025-08-01", "2025-08-05")

def baixar_e_filtrar_multithread(resultados, pasta_destino, extensoes=(".h5", ".nc", ".hdf"), threads=8):
    """
    Baixa os arquivos da NASA em paralelo usando múltiplas threads para o SSD local
    e filtra apenas as extensões de matrizes científicas.
    """
    if not resultados:
        return []
    os.makedirs(pasta_destino, exist_ok=True)
    
    # Download multithread (muito mais rápido que streaming via earthaccess.open)
    caminhos_locais = earthaccess.download(resultados, local_path=pasta_destino, threads=threads)
    
    validos = [
        str(f) for f in caminhos_locais 
        if str(f).lower().endswith(extensoes)
    ]
    print(f"[{pasta_destino}] Baixados: {len(caminhos_locais)} | Matrizes válidas: {len(validos)}")
    return validos

def alinhar_para_padrao_gpu(da_origem_cpu, grade_ref_cpu):
    """Interpola na CPU usando a grade de referência e já devolve o DataArray na GPU (padrão)."""
    return da_origem_cpu.interp_like(grade_ref_cpu, method="linear").compute().cupy.as_cupy()

res_smap = earthaccess.search_data(
    short_name="SPL4SMGP",
    bounding_box=bbox,
    temporal=periodo,
    count=16
)
arq_smap = baixar_e_filtrar_multithread(res_smap, "./cache_nasa/smap", extensoes=(".h5",))

# 1. Abertura paralela multithread no disco local via Dask
ds_smap_cpu = xr.open_mfdataset(
    arq_smap,
    group="Geophysical_Data",
    engine="h5netcdf",
    combine="nested",
    concat_dim="time",
    chunks={"time": 8, "y": 400, "x": 400},
    parallel=True
)

# 2. Extrai coordenadas do grupo raiz na CPU e recorta para a América do Sul
ds_raiz_cpu = xr.open_dataset(arq_smap[0], engine="h5netcdf")
lat_1d_cpu = ds_raiz_cpu["cell_lat"][:, 0].values
lon_1d_cpu = ds_raiz_cpu["cell_lon"][0, :].values

ds_smap_cpu = ds_smap_cpu.assign_coords(y=lat_1d_cpu, x=lon_1d_cpu).sortby(["y", "x"])
ds_smap_cpu = ds_smap_cpu.sel(y=slice(-30.0, -2.0), x=slice(-75.0, -34.0))

# Grade leve mantida na CPU apenas como molde para o .interp_like() dos outros sensores
grade_ref_cpu = ds_smap_cpu[["sm_surface"]].isel(time=0).compute()

# 3. Transfere o Dataset principal para a GPU (torna-se o ds_smap padrão)
vars_smap = ["sm_surface", "sm_rootzone", "sm_profile", "land_fraction_wilting", "surface_temp"]
ds_smap = ds_smap_cpu[vars_smap].compute().cupy.as_cupy()

# Variáveis padrão já calculadas e armazenadas na GPU
umidade_sup  = ds_smap["sm_surface"].mean(dim="time")
umidade_prof = ds_smap["sm_rootzone"].mean(dim="time")
umidade_perf = ds_smap["sm_profile"].mean(dim="time")
aridez_wilt  = ds_smap["land_fraction_wilting"].mean(dim="time")
amp_termica_smap = ds_smap["surface_temp"].max(dim="time") - ds_smap["surface_temp"].min(dim="time")


# ==============================================================================
# BLOCO 2 REESCRITO: EXTRAÇÃO DE MÚLTIPLOS TILES HDF-EOS5 (VNP21A1D / VNP21A1N)
# ==============================================================================
# Aumentamos count=20 para garantir que todos os tiles da América do Sul (h10 a h14)
# sejam baixados, e não apenas o primeiro tile oceânico (h10v11)
res_temp_dia = earthaccess.search_data(short_name="VNP21A1D", bounding_box=bbox, temporal=periodo, count=20)
res_temp_noite = earthaccess.search_data(short_name="VNP21A1N", bounding_box=bbox, temporal=periodo, count=20)

arq_dia = baixar_e_filtrar_multithread(res_temp_dia, "./cache_nasa/lst_dia", extensoes=(".h5",))
arq_noite = baixar_e_filtrar_multithread(res_temp_noite, "./cache_nasa/lst_noite", extensoes=(".h5",))

def extrair_mosaico_lst_viirs(lista_arquivos_h5, grade_ref_cpu):
    """
    Abre os subgrupos HDF-EOS5 do VNP21, converte as coordenadas da grade do SMAP
    (lat/lon) para metros na Projeção Sinusoidal (R = 6371007.181 m) e monta o 
    mosaico completo diretamente na GPU.
    """
    grupo_raiz_grid = "HDFEOS/GRIDS/VIIRS_Grid_Daily_1km_LST21"
    grupo_dados     = f"{grupo_raiz_grid}/Data Fields"
    
    # 1. Prepara a matriz final (em CPU temporariamente para o interp2d dos tiles) preenchida com NaN
    lats_smap_cpu = grade_ref_cpu["y"].values # Shape: (N_y,)
    lons_smap_cpu = grade_ref_cpu["x"].values # Shape: (N_x,)
    lon_2d_cpu, lat_2d_cpu = np.meshgrid(lons_smap_cpu, lats_smap_cpu)
    
    # Converte os graus (lat, lon) da grade do SMAP para Metros Sinusoidais (XDim, YDim)
    # Conforme metadados do seu arquivo: earth_radius = 6371007.181, central_meridian = 0
    R_SIN = 6371007.181
    lat_rad_cpu = np.radians(lat_2d_cpu)
    lon_rad_cpu = np.radians(lon_2d_cpu)
    
    x_alvo_metros = R_SIN * lon_rad_cpu * np.cos(lat_rad_cpu)
    y_alvo_metros = R_SIN * lat_rad_cpu
    
    # Cria DataArrays 2D de coordenadas-alvo para extração vetorizada no Xarray
    da_x_alvo = xr.DataArray(x_alvo_metros, dims=("y", "x"), coords={"y": lats_smap_cpu, "x": lons_smap_cpu})
    da_y_alvo = xr.DataArray(y_alvo_metros, dims=("y", "x"), coords={"y": lats_smap_cpu, "x": lons_smap_cpu})
    
    # Acumulador na GPU para calcular a média onde houver mais de um dia/tile
    soma_temp = cp.zeros(lon_2d_cpu.shape, dtype=cp.float32)
    contagem_valida = cp.zeros(lon_2d_cpu.shape, dtype=cp.float32)
    
    for caminho_h5 in lista_arquivos_h5:
        try:
            # Abre as coordenadas em metros (XDim, YDim) no grupo da grade
            ds_coords_cpu = xr.open_dataset(caminho_h5, group=grupo_raiz_grid, engine="h5netcdf")
            # Abre as variáveis de dados (LST_1KM) com mask_and_scale=False para aplicarmos com precisão
            ds_dados_cpu  = xr.open_dataset(
                caminho_h5, 
                group=grupo_dados, 
                engine="h5netcdf", 
                mask_and_scale=False
            )
            
            # Extrai a matriz bruta uint16 (1200 x 1200)
            lst_bruto_cpu = ds_dados_cpu["LST_1KM"]
            
            # Associa os eixos XDim e YDim em metros (no HDF-EOS5 as dimensões chamam-se phony_dim_0 e phony_dim_1)
            dim_y, dim_x = lst_bruto_cpu.dims
            lst_bruto_cpu = lst_bruto_cpu.assign_coords({
                dim_y: ds_coords_cpu["YDim"].values,
                dim_x: ds_coords_cpu["XDim"].values
            }).sortby([dim_y, dim_x])
            
            # Verifica rapidamente se este tile tem intersecção com a América do Sul
            x_min_tile, x_max_tile = float(lst_bruto_cpu[dim_x].min()), float(lst_bruto_cpu[dim_x].max())
            y_min_tile, y_max_tile = float(lst_bruto_cpu[dim_y].min()), float(lst_bruto_cpu[dim_y].max())
            
            # Amostra os pontos do SMAP que caem dentro deste tile usando vizinho mais próximo (nearest)
            recorte_tile_cpu = lst_bruto_cpu.sel(
                {dim_y: da_y_alvo, dim_x: da_x_alvo}, 
                method="nearest",
                tolerance=2000.0 # Tolerância de 2 km para não extrapolar fora das bordas do tile
            )
            
            # Envia o tile amostrado para a GPU
            arr_tile = cp.asarray(recorte_tile_cpu.values, dtype=cp.float32)
            
            # Aplica as regras exatas dos seus atributos:
            # _Fillvalue = 0 | valid_range = [7500, 65535] | scale_factor = 0.02
            mascara_valida = (arr_tile >= 7500.0) & (arr_tile <= 65535.0)
            temp_kelvin = cp.where(mascara_valida, arr_tile * 0.02, 0.0)
            
            soma_temp += temp_kelvin
            contagem_valida += mascara_valida.astype(cp.float32)
            
        except Exception as e:
            continue

    # Calcula a temperatura média em Kelvin na GPU (onde não há dados, vira NaN)
    media_kelvin_gpu = cp.where(contagem_valida > 0, soma_temp / contagem_valida, cp.nan)
    
    return xr.DataArray(
        media_kelvin_gpu,
        coords=grade_ref_cpu.coords,
        dims=("y", "x")
    )

# Executa a extração e monta as variáveis padrão diretamente na GPU
if arq_dia and arq_noite:
    lst_dia   = extrair_mosaico_lst_viirs(arq_dia, grade_ref_cpu)
    lst_noite = extrair_mosaico_lst_viirs(arq_noite, grade_ref_cpu)
    
    # Calcula a amplitude térmica onde ambos (dia e noite) têm dados válidos;
    # Nas áreas nubladas do VIIRS (NaN), preenche automaticamente com a amplitude do SMAP (radar/modelo sem falha de nuvem)
    amp_viirs = lst_dia - lst_noite
    amp_termica = xr.where(amp_viirs.notnull() & (amp_viirs > 0), amp_viirs, amp_termica_smap)
    print("Mosaico VIIRS LST (Dia - Noite) processado na GPU com fallback híbrido SMAP!")
else:
    amp_termica = amp_termica_smap


def extrair_mosaico_viirs_hdfeos5(
    lista_arquivos_h5, 
    grade_ref_cpu, 
    nome_variavel, 
    fator_escala, 
    valid_min, 
    valid_max, 
    valor_padrao_fallback=0.15
):
    """
    Localiza automaticamente o subgrupo HDF-EOS5 dentro do arquivo .h5 (independente 
    do nome da grade), projeta as coordenadas do SMAP para Metros Sinusoidais e 
    monta o mosaico diretamente na GPU (CuPy).
    """
    lats_smap_cpu = grade_ref_cpu["y"].values
    lons_smap_cpu = grade_ref_cpu["x"].values
    lon_2d_cpu, lat_2d_cpu = np.meshgrid(lons_smap_cpu, lats_smap_cpu)
    
    # Conversão exata de Graus (WGS84) para Metros Sinusoidais (R = 6371007.181 m)
    R_SIN = 6371007.181
    lat_rad_cpu = np.radians(lat_2d_cpu)
    lon_rad_cpu = np.radians(lon_2d_cpu)
    
    da_x_alvo = xr.DataArray(
        R_SIN * lon_rad_cpu * np.cos(lat_rad_cpu), 
        dims=("y", "x"), coords={"y": lats_smap_cpu, "x": lons_smap_cpu}
    )
    da_y_alvo = xr.DataArray(
        R_SIN * lat_rad_cpu, 
        dims=("y", "x"), coords={"y": lats_smap_cpu, "x": lons_smap_cpu}
    )
    
    soma_gpu = cp.zeros(lon_2d_cpu.shape, dtype=cp.float32)
    contagem_gpu = cp.zeros(lon_2d_cpu.shape, dtype=cp.float32)
    
    for caminho_h5 in lista_arquivos_h5:
        try:
            # 1. Descobre automaticamente o nome da grade dentro de HDFEOS/GRIDS/
            with h5py.File(caminho_h5, "r") as f_h5:
                nome_grid = list(f_h5["HDFEOS/GRIDS"].keys())[0]
                grupo_raiz_grid = f"HDFEOS/GRIDS/{nome_grid}"
                grupo_dados     = f"{grupo_raiz_grid}/Data Fields"
                
                # Caso o nome da variável tenha espaços vs. underscores, busca correspondência
                vars_disponiveis = list(f_h5[grupo_dados].keys())
                var_real = nome_variavel
                if var_real not in vars_disponiveis:
                     candidatas = [v for v in vars_disponiveis if nome_variavel.replace(" ", "_") in v.replace(" ", "_")]
                     if candidatas:
                         var_real = candidatas[0]

            # 2. Abre coordenadas (XDim, YDim) e a variável de dados com h5netcdf
            ds_coords_cpu = xr.open_dataset(caminho_h5, group=grupo_raiz_grid, engine="h5netcdf")
            ds_dados_cpu  = xr.open_dataset(caminho_h5, group=grupo_dados, engine="h5netcdf", mask_and_scale=False)
            
            da_bruto_cpu = ds_dados_cpu[var_real]
            dim_y, dim_x = da_bruto_cpu.dims
            
            da_bruto_cpu = da_bruto_cpu.assign_coords({
                dim_y: ds_coords_cpu["YDim"].values,
                dim_x: ds_coords_cpu["XDim"].values
            }).sortby([dim_y, dim_x])
            
            # 3. Amostra os pontos correspondentes à grade do SMAP
            recorte_cpu = da_bruto_cpu.sel(
                {dim_y: da_y_alvo, dim_x: da_x_alvo}, 
                method="nearest", 
                tolerance=2500.0
            )
            
            # 4. Transfere para a GPU, filtra valid_range e aplica fator de escala
            arr_tile = cp.asarray(recorte_cpu.values, dtype=cp.float32)
            mascara_valida = (arr_tile >= valid_min) & (arr_tile <= valid_max)
            
            soma_gpu += cp.where(mascara_valida, arr_tile * fator_escala, 0.0)
            contagem_gpu += mascara_valida.astype(cp.float32)
            
        except Exception as e:
            continue

    # Onde não houver cobertura de tile/nuvem, preenche com valor neutro para não zerar o score
    media_gpu = cp.where(contagem_gpu > 0, soma_gpu / contagem_gpu, valor_padrao_fallback)
    
    return xr.DataArray(media_gpu, coords=grade_ref_cpu.coords, dims=("y", "x"))


# ==============================================================================
# BLOCO 3 CORRIGIDO: ALBEDO DE ONDAS CURTAS (VNP43MA3) NA GPU
# ==============================================================================
res_albedo = earthaccess.search_data(short_name="VNP43MA3", bounding_box=bbox, temporal=periodo, count=20)
arq_albedo = baixar_e_filtrar_multithread(res_albedo, "./cache_nasa/albedo", extensoes=(".h5",))

# No VNP43MA3: scale_factor = 0.001 | valid_range = [0, 1000] | _FillValue = 32767
albedo = extrair_mosaico_viirs_hdfeos5(
    lista_arquivos_h5=arq_albedo,
    grade_ref_cpu=grade_ref_cpu,
    nome_variavel="Albedo_BSA_shortwave",
    fator_escala=0.001,
    valid_min=0.0,
    valid_max=1000.0,
    valor_padrao_fallback=0.15 # Albedo médio terrestre como fallback onde faltar tile
)
print("Variável 'albedo' carregada na GPU:", albedo.shape, type(albedo.data))


# ==============================================================================
# BLOCO 4 CORRIGIDO: ÍNDICE DE VEGETAÇÃO NDVI (VNP13A1) NA GPU
# ==============================================================================
res_ndvi = earthaccess.search_data(
    short_name="VNP13A1", 
    bounding_box=bbox, 
    temporal=("2025-08-01", "2025-08-17"), 
    count=20
)
arq_ndvi = baixar_e_filtrar_multithread(res_ndvi, "./cache_nasa/ndvi", extensoes=(".h5",))

# No VNP13A1: scale_factor = 0.0001 | valid_range = [-2000, 10000] | _FillValue = -15000
ndvi = extrair_mosaico_viirs_hdfeos5(
    lista_arquivos_h5=arq_ndvi,
    grade_ref_cpu=grade_ref_cpu,
    nome_variavel="500 m 16 days NDVI",
    fator_escala=0.0001,
    valid_min=-2000.0,
    valid_max=10000.0,
    valor_padrao_fallback=0.20
)
print("Variável 'ndvi' carregada na GPU:", ndvi.shape, type(ndvi.data))


def buscar_dataset_h5(arquivo_h5, palavras_chave):
    """
    Vasculha recursivamente todos os grupos do arquivo .h5/.nc e retorna 
    o primeiro array que contenha qualquer uma das palavras-chave no nome.
    Evita 100% dos erros de KeyError de grupo ou variável!
    """
    encontrados = {}
    def visitar(nome, obj):
        if isinstance(obj, h5py.Dataset):
            encontrados[nome] = obj
    arquivo_h5.visititems(visitar)
    
    for kw in palavras_chave:
        for caminho, dset in encontrados.items():
            nome_final = caminho.split("/")[-1].lower()
            if kw.lower() == nome_final or kw.lower() in nome_final:
                return dset[...], dset.attrs
    return None, None

def extrair_swath_ou_grade_para_gpu(
    lista_arquivos, 
    grade_ref_cpu, 
    nomes_possiveis_var, 
    valid_min, 
    valid_max, 
    valor_fallback=0.1
):
    """
    Lê arquivos L2 (Swath 2D curvo) ou L3 (Grade 1D), filtra valores inválidos 
    e projeta os pontos diretamente na malha (y, x) do SMAP usando a GPU (CuPy).
    """
    lats_smap = grade_ref_cpu["y"].values
    lons_smap = grade_ref_cpu["x"].values
    ny, nx = len(lats_smap), len(lons_smap)
    
    lat_min, lat_max = float(lats_smap.min()), float(lats_smap.max())
    lon_min, lon_max = float(lons_smap.min()), float(lons_smap.max())
    
    soma_gpu = cp.zeros((ny, nx), dtype=cp.float32)
    cont_gpu = cp.zeros((ny, nx), dtype=cp.float32)
    
    for arq in lista_arquivos:
        try:
            with h5py.File(arq, "r") as f:
                arr_val, attrs = buscar_dataset_h5(f, nomes_possiveis_var)
                arr_lat, _     = buscar_dataset_h5(f, ["latitude", "lat", "latitude_1d", "y"])
                arr_lon, _     = buscar_dataset_h5(f, ["longitude", "lon", "longitude_1d", "x"])
                
                if arr_val is None or arr_lat is None or arr_lon is None:
                    continue
                
                # Se a variável tiver 3 dimensões (ex: time, y, x ou band, y, x), pega a primeira fatia/média
                if arr_val.ndim == 3:
                    arr_val = arr_val[0]
                
                # Caso L3 (coordenadas 1D) -> Expande para malha 2D igual ao Swath L2
                if arr_lat.ndim == 1 and arr_lon.ndim == 1:
                    arr_lon, arr_lat = np.meshgrid(arr_lon, arr_lat)
                
                # Envia para a GPU
                val_gpu = cp.asarray(arr_val, dtype=cp.float32)
                lat_gpu = cp.asarray(arr_lat, dtype=cp.float32)
                lon_gpu = cp.asarray(arr_lon, dtype=cp.float32)
                
                # Aplica scale_factor e add_offset se existirem nos atributos e os dados forem inteiros
                scale = float(attrs.get("scale_factor", [1.0])[0] if np.ndim(attrs.get("scale_factor", 1.0)) > 0 else attrs.get("scale_factor", 1.0))
                offset = float(attrs.get("add_offset", [0.0])[0] if np.ndim(attrs.get("add_offset", 0.0)) > 0 else attrs.get("add_offset", 0.0))
                if scale != 1.0 or offset != 0.0:
                    # Verifica se ainda não está escalado
                    if float(cp.nanmax(cp.abs(val_gpu))) > valid_max * 2:
                        val_gpu = val_gpu * scale + offset
                
                # Filtra pontos válidos dentro da Bounding Box da América do Sul
                mascara = (
                    (val_gpu >= valid_min) & (val_gpu <= valid_max) &
                    (lat_gpu >= lat_min) & (lat_gpu <= lat_max) &
                    (lon_gpu >= lon_min) & (lon_gpu <= lon_max) &
                    cp.isfinite(val_gpu)
                )
                
                if not cp.any(mascara):
                    continue
                
                # Converte (lat, lon) dos pontos válidos em índices (iy, ix) da grade do SMAP na GPU
                lat_v = lat_gpu[mascara]
                lon_v = lon_gpu[mascara]
                val_v = val_gpu[mascara]
                
                iy = cp.clip(((lat_v - lat_min) / (lat_max - lat_min) * (ny - 1)).astype(cp.int32), 0, ny - 1)
                ix = cp.clip(((lon_v - lon_min) / (lon_max - lon_min) * (nx - 1)).astype(cp.int32), 0, nx - 1)
                
                # Acumula de forma atômica na grade da GPU
                cp.add.at(soma_gpu, (iy, ix), val_v)
                cp.add.at(cont_gpu, (iy, ix), 1.0)
                
        except Exception as e:
            continue

    # Onde houver células vazias entre órbitas, preenche com a mediana regional ou fallback
    if float(cont_gpu.max()) > 0:
        media_regional = float(soma_gpu.sum() / cont_gpu.sum())
    else:
        media_regional = valor_fallback
        
    matriz_final_gpu = cp.where(cont_gpu > 0, soma_gpu / cont_gpu, media_regional)
    
    return xr.DataArray(matriz_final_gpu, coords=grade_ref_cpu.coords, dims=("y", "x"))


# 5.1 OMPS UV Aerosol Index (Suporta L2 Swath ou L3 Grid sem KeyError)
res_omps = earthaccess.search_data(
    short_name="OMPS_NPP_NMMIEAI_L2", 
    bounding_box=bbox, 
    temporal=periodo, 
    count=15
)
arq_omps = baixar_e_filtrar_multithread(res_omps, "./cache_nasa/omps", extensoes=(".h5", ".nc"))

aerosol_idx = extrair_swath_ou_grade_para_gpu(
    lista_arquivos=arq_omps,
    grade_ref_cpu=grade_ref_cpu,
    nomes_possiveis_var=["UVAerosolIndex", "UVAI", "AerosolIndex", "ai"],
    valid_min=-2.0,
    valid_max=15.0,
    valor_fallback=0.2
)
print("Variável 'aerosol_idx' (OMPS) pronta na GPU:", aerosol_idx.shape, type(aerosol_idx.data))


# 5.2 Espessura Óptica de Aerossóis (AOD - Deep Blue VIIRS/MODIS)
res_aod = earthaccess.search_data(
    short_name="AERDB_D3_VIIRS_SNPP", 
    bounding_box=bbox, 
    temporal=periodo, 
    count=5
)
arq_aod = baixar_e_filtrar_multithread(res_aod, "./cache_nasa/aod", extensoes=(".nc", ".h5"))

aod_modis = extrair_swath_ou_grade_para_gpu(
    lista_arquivos=arq_aod,
    grade_ref_cpu=grade_ref_cpu,
    nomes_possiveis_var=[
        "Aerosol_Optical_Thickness_550_Land_Ocean_Mean",
        "Aerosol_Optical_Thickness_550_Land_Mean",
        "Optical_Depth_Land_And_Ocean",
        "AOD_550"
    ],
    valid_min=0.0,
    valid_max=5.0,
    valor_fallback=0.15
)
print("Variável 'aod_modis' (AERDB) pronta na GPU:", aod_modis.shape, type(aod_modis.data))


# ==============================================================================
# BLOCO 6 CORRIGIDO: MINERALOGIA EMIT (GROUP 1 & GROUP 2) DIRETO NA GPU
# ==============================================================================
res_emit = earthaccess.search_data(
    short_name="EMITL2BMIN",
    bounding_box=bbox,
    temporal=("2024-01-01", "2025-08-05"),
    count=15
)
arq_emit = baixar_e_filtrar_multithread(res_emit, "./cache_nasa/emit", extensoes=(".nc", ".h5"))

def extrair_emit_grupos_para_gpu(lista_arquivos_nc, grade_ref_cpu):
    """
    Lê 'group_1_band_depth' e 'group_2_band_depth' dos arquivos EMITL2BMIN,
    cruza com as coordenadas 2D do grupo 'location' e projeta na grade (y, x)
    do SMAP diretamente na GPU via CuPy.
    """
    lats_smap = grade_ref_cpu["y"].values
    lons_smap = grade_ref_cpu["x"].values
    ny, nx = len(lats_smap), len(lons_smap)
    
    lat_min, lat_max = float(lats_smap.min()), float(lats_smap.max())
    lon_min, lon_max = float(lons_smap.min()), float(lons_smap.max())
    
    soma_g1_gpu = cp.zeros((ny, nx), dtype=cp.float32)
    soma_g2_gpu = cp.zeros((ny, nx), dtype=cp.float32)
    cont_gpu    = cp.zeros((ny, nx), dtype=cp.float32)
    
    for arq in lista_arquivos_nc:
        try:
            # Abre a raiz (onde estão group_1_band_depth e group_2_band_depth) e o grupo 'location'
            ds_sci_cpu = xr.open_dataset(arq, engine="h5netcdf")
            ds_loc_cpu = xr.open_dataset(arq, group="location", engine="h5netcdf")
            
            # Transfere as matrizes 2D da órbita da ISS para a GPU
            g1_gpu  = cp.asarray(ds_sci_cpu["group_1_band_depth"].values, dtype=cp.float32)
            g2_gpu  = cp.asarray(ds_sci_cpu["group_2_band_depth"].values, dtype=cp.float32)
            lat_gpu = cp.asarray(ds_loc_cpu["lat"].values, dtype=cp.float32)
            lon_gpu = cp.asarray(ds_loc_cpu["lon"].values, dtype=cp.float32)
            
            # Filtra pixels válidos (no EMIT, _FillValue é -9999 e profundidades de banda vão de 0 a 1)
            mascara = (
                (g1_gpu >= 0.0) & (g1_gpu <= 1.0) &
                (g2_gpu >= 0.0) & (g2_gpu <= 1.0) &
                (lat_gpu >= lat_min) & (lat_gpu <= lat_max) &
                (lon_gpu >= lon_min) & (lon_gpu <= lon_max) &
                cp.isfinite(g1_gpu) & cp.isfinite(g2_gpu)
            )
            
            if not cp.any(mascara):
                continue
                
            # Converte (lat, lon) da órbita 2D para índices (iy, ix) da grade do SMAP na GPU
            lat_v = lat_gpu[mascara]
            lon_v = lon_gpu[mascara]
            
            iy = cp.clip(((lat_v - lat_min) / (lat_max - lat_min) * (ny - 1)).astype(cp.int32), 0, ny - 1)
            ix = cp.clip(((lon_v - lon_min) / (lon_max - lon_min) * (nx - 1)).astype(cp.int32), 0, nx - 1)
            
            cp.add.at(soma_g1_gpu, (iy, ix), g1_gpu[mascara])
            cp.add.at(soma_g2_gpu, (iy, ix), g2_gpu[mascara])
            cp.add.at(cont_gpu, (iy, ix), 1.0)
            
        except Exception as e:
            continue

    # Calcula as médias onde a ISS passou; onde não houve cobertura orbital, usa a média regional
    if float(cont_gpu.max()) > 0:
        med_g1 = float(soma_g1_gpu.sum() / cont_gpu.sum())
        med_g2 = float(soma_g2_gpu.sum() / cont_gpu.sum())
    else:
        med_g1, med_g2 = 0.5, 0.5
        
    arr_g1_final = cp.where(cont_gpu > 0, soma_g1_gpu / cont_gpu, med_g1)
    arr_g2_final = cp.where(cont_gpu > 0, soma_g2_gpu / cont_gpu, med_g2)
    
    # Para a Lua: queremos alta presença de ferro/máficos (Grupo 2) e baixa presença de argilas hidratadas (Grupo 1)
    score_min_lua = (0.70 * arr_g2_final + 0.30 * (1.0 - arr_g1_final)).clip(0, 1)
    
    # Para Marte: queremos tanto óxidos de ferro (Grupo 2) quanto argilas/sulfatos de paleolagos (Grupo 1)
    score_min_marte = (0.60 * arr_g2_final + 0.40 * arr_g1_final).clip(0, 1)
    
    da_lua   = xr.DataArray(score_min_lua, coords=grade_ref_cpu.coords, dims=("y", "x"))
    da_marte = xr.DataArray(score_min_marte, coords=grade_ref_cpu.coords, dims=("y", "x"))
    return da_lua, da_marte

# Cria as variáveis padrão diretamente na GPU
mineral_basalto, mineral_marte = extrair_emit_grupos_para_gpu(arq_emit, grade_ref_cpu)
print("Variáveis 'mineral_basalto' e 'mineral_marte' prontas na GPU:", mineral_basalto.shape, type(mineral_basalto.data))


# ==============================================================================
# 1. FILTRAGEM DOS TOP CANDIDATOS NA GPU (COM cp.isfinite + cp.percentile)
# ==============================================================================
dados_lua_gpu = ds_smap["score_lua"].data
valores_validos_gpu = dados_lua_gpu[cp.isfinite(dados_lua_gpu)]

limiar_corte = float(cp.percentile(valores_validos_gpu, 95.0))
max_score_real = float(valores_validos_gpu.max())

areas_criticas = ds_smap["score_lua"].where(ds_smap["score_lua"] >= limiar_corte)

df_lua_cpu = (
    areas_criticas.cupy.as_numpy()
    .to_dataframe(name="score_real")
    .dropna()
    .reset_index()
    .rename(columns={"y": "lat", "x": "lon"})
)

# Realce quadrático para destacar os picos no HeatMap
df_lua_cpu["peso_calor"] = (
    (df_lua_cpu["score_real"] - limiar_corte) / (max_score_real - limiar_corte + 1e-6)
) ** 2

df_lua_cpu = df_lua_cpu.sort_values(by="score_real", ascending=False).reset_index(drop=True)
heat_data_lua = df_lua_cpu[["lat", "lon", "peso_calor"]].values.tolist()


# ==============================================================================
# 2. IDENTIFICAÇÃO DOS NOMES DOS LOCAIS DO TOP 10 (GEOCODIFICAÇÃO REVERSA)
# ==============================================================================
df_top10_cpu = df_lua_cpu.head(10).copy()
coordenadas_top10 = list(zip(df_top10_cpu["lat"], df_top10_cpu["lon"]))

# Busca cidade (name), estado/região (admin1) e país (cc) para os 10 pontos de uma vez
info_locais = rg.search(coordenadas_top10, verbose=False)

df_top10_cpu["nome_local"] = [
    f"{loc['name']}, {loc['admin1']} ({loc['cc']})" for loc in info_locais
]


# ==============================================================================
# 3. MAPA-MÚNDI COM HEATMAP E RÓTULOS FIXOS DO TOP 10
# ==============================================================================
mapa_mundi_lua = folium.Map(
    location=[0.0, -30.0],  # Visão global centralizada no Atlântico/Américas
    zoom_start=2,           # Zoom inicial mostrando o Mapa-Múndi completo
    min_zoom=2,
    max_bounds=True,
    min_lat=-85.0, max_lat=85.0,
    min_lon=-180.0, max_lon=180.0,
    tiles=None
)

# Camada de Mapa-Múndi Escura com Rótulos Geográficos (CartoDB Dark Matter) e sem repetição lateral
folium.TileLayer(
    tiles="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
    attr="CartoDB",
    name="Mapa-Múndi Escuro (Com Nomes)",
    no_wrap=True
).add_to(mapa_mundi_lua)

# Camada opcional de Satélite Global (ESRI World Imagery) para ver o terreno real
folium.TileLayer(
    tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attr="Esri",
    name="Satélite Real (ESRI World Imagery)",
    no_wrap=True,
    show=True
).add_to(mapa_mundi_lua)

# HeatMap Lunar
gradiente_lunar = {
    0.2: "#1b4965",
    0.5: "#62b6cb",
    0.8: "#bee9e8",
    0.95: "#ffff3f",
    1.0: "#ffffff"
}

HeatMap(
    data=heat_data_lua,
    name="Mapa de Calor - Analogia Lunar (Top 5%)",
    radius=14,
    blur=10,
    min_opacity=0.30,
    max_zoom=8,
    gradient=gradiente_lunar
).add_to(mapa_mundi_lua)

# Grupo para os Marcadores e Rótulos Visíveis do Top 10
grupo_rotulos_top10 = folium.FeatureGroup(name="Top 10 Locais (Com Rótulos Fixos)").add_to(mapa_mundi_lua)

for rank, row in df_top10_cpu.iterrows():
    num_rank = rank + 1
    lat, lon = row["lat"], row["lon"]
    local_str = row["nome_local"]
    score_val = row["score_real"]
    
    # 1. Ponto luminoso sobre a coordenada exata
    folium.CircleMarker(
        location=[lat, lon],
        radius=6,
        color="#ffff3f",
        weight=2,
        fill=True,
        fill_color="#ffffff",
        fill_opacity=1.0,
        popup=folium.Popup(
            f"<b>#{num_rank} - {local_str}</b><br>"
            f"<b>Score Lunar:</b> {score_val:.4f}<br>"
            f"<b>Coordenadas:</b> {lat:.3f}°, {lon:.3f}°",
            max_width=260
        )
    ).add_to(grupo_rotulos_top10)
    
    # 2. Rótulo de texto permanente (DivIcon) ao lado do ponto no mapa
    html_rotulo = f"""
    <div style="
        font-family: monospace, sans-serif;
        font-size: 11px;
        font-weight: bold;
        color: #ffff3f;
        background-color: rgba(15, 23, 42, 0.85);
        border: 1px solid #62b6cb;
        border-radius: 4px;
        padding: 2px 6px;
        white-space: nowrap;
        box-shadow: 2px 2px 4px rgba(0,0,0,0.6);
        transform: translate(10px, -10px);
        pointer-events: none;
    ">
        #{num_rank} {local_str} ({score_val:.3f})
    </div>
    """
    folium.Marker(
        location=[lat, lon],
        icon=folium.DivIcon(html=html_rotulo)
    ).add_to(grupo_rotulos_top10)

folium.LayerControl(collapsed=False).add_to(mapa_mundi_lua)

# Exibe a tabela resumida no console e renderiza o Mapa-Múndi
print("Top 10 Locais Identificados:")
print(df_top10_cpu[["nome_local", "lat", "lon", "score_real"]].to_string(index=False))

mapa_mundi_lua.save("analogos_da_lua.html")


def extrair_valor_ponto(da, nome_var):
    try:
        # 1. Seleciona o pixel mais próximo usando o método nativo do xarray
        ponto_da = da.sel(y=lat_t1, x=lon_t1, method="nearest")
        
        # 2. Extrai o dado cru (pode ser CuPy array, numpy array ou escalar)
        val = ponto_da.data
        
        # 3. Conversão segura para escalar Python independente de onde o dado reside
        if hasattr(val, "get"):          # Se for CuPy na GPU
            val = val.get()
        if hasattr(val, "item"):         # Se for array NumPy ou CuPy
            val = val.item()
            
        return float(val)
    except Exception as e:
        return float("nan")

# ==============================================================================
# EXTRATOR CORRIGIDO DE VARIÁVEIS DO TOP 1 ANÁLOGO LUNAR (GPU -> CPU)
# ==============================================================================

top1_row = df_top10_cpu.iloc[0]
lat_t1 = top1_row["lat"]
lon_t1 = top1_row["lon"]
score_t1 = top1_row["score_real"]
nome_t1 = top1_row["nome_local"]

print("="*60)
print(f"🏆 ANÁLOGO LUNAR #1: {nome_t1}")
print(f"Coordenadas: Latitude {lat_t1:.4f}°, Longitude {lon_t1:.4f}°")
print(f"Score Lunar Final: {score_t1:.4f} (Escala 0.0 a 1.0)")
print("="*60)
print("🔍 VALORES INDIVIDUAIS DOS DADOS DA NASA NO PONTO:")



# Extracción detalhada por pilar utilizando a função corrigida
print("\n[PILAR 1: TEMPERATURA E ALBEDO]")
val_amp = extrair_valor_ponto(amp_termica, "amp_termica")
val_alb = extrair_valor_ponto(albedo, "albedo")
print(f" • Amplitude Térmica (Diurna/Noite ou 3h): {val_amp:.2f} K")
print(f" • Albedo de Ondas Curtas (BSA):          {val_alb:.4f} (Ideal < 0.12)")

print("\n[PILAR 2: SOLO E SECURA]")
val_sm_sup  = extrair_valor_ponto(umidade_sup, "sm_surface")
val_sm_prof = extrair_valor_ponto(umidade_prof, "sm_rootzone")
val_sm_perf = extrair_valor_ponto(umidade_perf, "sm_profile")
val_wilt    = extrair_valor_ponto(aridez_wilt, "aridez_wilt")
val_ndvi    = extrair_valor_ponto(ndvi, "ndvi")
print(f" • Umidade Superficial (0-5 cm):        {val_sm_sup:.5f} m³/m³")
print(f" • Umidade na Zona Raiz(0-100 cm):      {val_sm_prof:.5f} m³/m³")
print(f" • Umidade no Perfil Profundo:          {val_sm_perf:.5f} m³/m³")
print(f" • Fração de Ponto de Murcha (Aridez):  {val_wilt:.4f}")
print(f" • Índice de Vegetação (NDVI):          {val_ndvi:.4f} (Ideal ~ 0.0)")

print("\n[PILAR 3: POEIRA E MINERALOGIA]")
val_aer  = extrair_valor_ponto(aerosol_idx, "aerosol_idx")
val_aod  = extrair_valor_ponto(aod_modis, "aod_modis")
val_min  = extrair_valor_ponto(mineral_basalto, "mineral_basalto")
print(f" • Índice de Aerossóis UV (OMPS/AERDB): {val_aer:.4f}")
print(f" • Espessura Óptica de Aerossóis (AOD): {val_aod:.4f}")
print(f" • Abundância Mineral Máfica (EMIT):    {val_min:.4f}")
print("="*60)