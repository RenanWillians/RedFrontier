/* =====================================================
   SPACE EXPLORER
   Space Quiz Logic
===================================================== */


/* 1. QUESTION BANK */

const questions = [

    {
        question:
            "What is the main difference between the Moon's temperature and Earth's temperature?",

        answers: [
            "The Moon's temperature has extreme heat and cold.",
            "The Moon's temperature is the same as Earth's.",
            "The Moon's temperature is half as low as Earth's."
        ],

        correct: 0,

        explanation:
            "The Moon has no atmosphere, so it heats up significantly under the Sun and becomes extremely cold in the shade, creating extreme temperatures that do not occur on Earth."
    },

    {
        question:
            "Which characteristic of Mars most closely resembles an arid condition found on Earth?",

        answers: [
            "The existence of seasons, just like on Earth.",
            "Sandstorms in the driest regions.",
            "The presence of an oxygen-rich atmosphere."
        ],

        correct: 1,

        explanation:
            "The correct answer is “Sandstorms in the driest regions” because Mars is extremely arid, and its dust storms resemble those that occur in Earth's deserts."
    },
];


/* 2. GAME STATE */

let currentQuestion = 0;
let score = 0;

let selectedAnswer = null;
let answered = false;


/* 3. HTML ELEMENTS */

const quizPanel = document.getElementById("quiz-panel");
const resultScreen = document.getElementById("result-screen");

const questionElement = document.getElementById("question");
const questionNumber = document.getElementById("question-number");

const answersElement = document.getElementById("answers");

const progressElement = document.getElementById("progress");
const progressFill = document.getElementById("progress-fill");
const progressContainer = document.getElementById("progress-container");

const submitButton = document.getElementById("submit-button");
const nextButton = document.getElementById("next-button");

const feedbackBox = document.getElementById("feedback-box");
const feedbackTitle = document.getElementById("feedback-title");
const feedbackIcon = document.getElementById("feedback-icon");
const feedbackText = document.getElementById("feedback");

const correctAnswerBox = document.getElementById("correct-answer");
const correctAnswerText = document.getElementById("correct-answer-text");

const alienMessage = document.getElementById("alien-message");
const guideTitle = document.getElementById("guide-title");

const finalScore = document.getElementById("final-score");
const scoreNumber = document.getElementById("score-number");
const scoreFill = document.getElementById("score-fill");
const resultDetails = document.getElementById("result-details");

const restartButton = document.getElementById("restart-button");


/* 4. ELEMENT VALIDATION */

const requiredElements = [
    quizPanel,
    resultScreen,
    questionElement,
    questionNumber,
    answersElement,
    progressElement,
    progressFill,
    progressContainer,
    submitButton,
    nextButton,
    feedbackBox,
    feedbackTitle,
    feedbackIcon,
    feedbackText,
    correctAnswerBox,
    correctAnswerText,
    alienMessage,
    guideTitle,
    finalScore,
    scoreNumber,
    scoreFill,
    resultDetails,
    restartButton
];

const elementsAreValid = requiredElements.every(
    element => element !== null
);


/* 5. UPDATE THE PROGRESS BAR */

function updateProgress() {

    // Calculates the percentage of questions completed
    const percentage =
        (currentQuestion / questions.length) * 100;

    progressFill.style.width = `${percentage}%`;

    // Displays the current question and the total number
    progressElement.textContent =
        `${String(currentQuestion + 1).padStart(2, "0")} / ${String(questions.length).padStart(2, "0")}`;

    // Updates the accessible progress bar value
    progressContainer.setAttribute(
        "aria-valuenow",
        currentQuestion
    );

}


/* 6. LOAD A QUESTION */

function showQuestion() {

    // Resets the question controls
    selectedAnswer = null;
    answered = false;

    // Gets the current question data
    const question = questions[currentQuestion];

    // Updates the question text
    questionElement.textContent = question.question;

    questionNumber.textContent =
        `QUESTION ${String(currentQuestion + 1).padStart(2, "0")}`;

    // Updates the progress
    updateProgress();

    // Updates the alien's dialogue
    guideTitle.textContent = "Your turn, explorer!";

    alienMessage.textContent =
        "Read the options carefully. When you have made your decision, select your answer and click Submit Answer.";

    // Clears the previous answer options
    answersElement.innerHTML = "";

    // Hides the previous feedback
    feedbackBox.hidden = true;
    feedbackBox.className = "feedback-panel";

    correctAnswerBox.hidden = true;

    // Hides the next button
    nextButton.hidden = true;

    // Makes the submit button visible but disabled
    submitButton.hidden = false;
    submitButton.disabled = true;

    // Creates the answer option buttons
    question.answers.forEach((answer, index) => {

        const button = document.createElement("button");

        button.type = "button";
        button.className = "answer-option";

        // Creates the answer letter
        const letter = document.createElement("span");

        letter.className = "answer-letter";
        letter.textContent = String.fromCharCode(65 + index);

        // Creates the answer text
        const text = document.createElement("span");

        text.textContent = answer;

        // Builds the button
        button.appendChild(letter);
        button.appendChild(text);

        // Registers the selected answer
        button.addEventListener("click", () => {
            selectAnswer(index, button);
        });

        answersElement.appendChild(button);

    });

}


/* 7. SELECT AN ANSWER */

function selectAnswer(index, selectedButton) {

    // Prevents changing the answer after submission
    if (answered) return;

    selectedAnswer = index;

    // Removes the previous visual selection
    const allButtons =
        answersElement.querySelectorAll(".answer-option");

    allButtons.forEach(button => {
        button.classList.remove("selected");
    });

    // Highlights the selected option
    selectedButton.classList.add("selected");

    // Enables the submit button
    submitButton.disabled = false;

}


/* 8. SUBMIT AND EVALUATE THE ANSWER */

function submitAnswer() {

    // Prevents submission without a selection
    if (selectedAnswer === null || answered) return;

    answered = true;

    const question = questions[currentQuestion];

    const allButtons =
        answersElement.querySelectorAll(".answer-option");

    const isCorrect =
        selectedAnswer === question.correct;

    // Disables all answer options
    allButtons.forEach(button => {
        button.disabled = true;
    });

    // Disables the submit button
    submitButton.disabled = true;
    submitButton.hidden = true;

    // Highlights the correct answer
    allButtons[question.correct].classList.add("correct");

    // Displays the feedback panel
    feedbackBox.hidden = false;

    // Displays the scientific explanation
    feedbackText.textContent = question.explanation;

    if (isCorrect) {

        // Adds one point
        score++;

        // Configures green feedback
        feedbackBox.className =
            "feedback-panel is-correct";

        feedbackIcon.textContent = "✓";
        feedbackTitle.textContent = "Correct answer!";

        // Updates the alien's dialogue
        guideTitle.textContent = "Well done, explorer!";

        alienMessage.textContent =
            "Excellent! You got it right. Keep it up and complete your space mission!";

        // There is no need to show the correct answer again
        correctAnswerBox.hidden = true;

    } else {

        // Highlights the selected option as incorrect
        allButtons[selectedAnswer].classList.add("incorrect");

        // Configures red feedback
        feedbackBox.className =
            "feedback-panel is-incorrect";

        feedbackIcon.textContent = "✕";
        feedbackTitle.textContent = "Incorrect answer!";

        // Updates the alien's dialogue
        guideTitle.textContent = "Let's learn together!";

        alienMessage.textContent =
            "Don't give up! Making mistakes is also part of exploration and discovery.";

        // Shows which option was correct
        const correctLetter =
            String.fromCharCode(65 + question.correct);

        correctAnswerText.textContent =
            `${correctLetter}) ${question.answers[question.correct]}`;

        correctAnswerBox.hidden = false;

    }

    // Displays the next button
    nextButton.hidden = false;

    // Changes the text on the last question
    if (currentQuestion === questions.length - 1) {

        nextButton.innerHTML =
            'View final result <span aria-hidden="true">🏆</span>';

    } else {

        nextButton.innerHTML =
            'Next question <span aria-hidden="true">➜</span>';

    }

}


/* 9. MOVE TO THE NEXT QUESTION */

function nextQuestion() {

    // Only advances after an answer has been submitted
    if (!answered) return;

    currentQuestion++;

    // Checks whether there are still questions remaining
    if (currentQuestion < questions.length) {

        showQuestion();

    } else {

        showResult();

    }

}


/* 10. DISPLAY THE FINAL RESULT */

function showResult() {

    // Completes the progress bar
    progressFill.style.width = "100%";

    progressContainer.setAttribute(
        "aria-valuenow",
        questions.length
    );

    // Hides the quiz panel
    quizPanel.hidden = true;

    // Displays the final screen
    resultScreen.hidden = false;

    // Calculates the percentage of correct answers
    const percentage =
        (score / questions.length) * 100;

    // Displays the score
    finalScore.textContent =
        `You answered ${score} out of ${questions.length} questions correctly.`;

    scoreNumber.textContent =
        `${score}/${questions.length}`;

    scoreFill.style.width = `${percentage}%`;

    // Displays a message according to the result
    if (score === questions.length) {

        resultDetails.textContent =
            "🌟 Excellent! You demonstrated incredible knowledge about the Moon, Mars, and Earth!";

    } else if (score >= 2) {

        resultDetails.textContent =
            "🚀 Well done! You are on your way to becoming a great space explorer.";

    } else {

        resultDetails.textContent =
            "🌎 Keep learning! Every discovery is another step forward in exploring the universe.";

    }

    // Updates the alien's dialogue
    guideTitle.textContent = "Mission completed!";

    alienMessage.textContent =
        "It was an incredible adventure! I hope to see you again on another space mission.";

    // Saves the score without preventing the game from continuing if storage fails
    try {

        localStorage.setItem("quizScore", String(score));

    } catch (error) {

        console.warn(
            "Unable to save the score in the browser.",
            error
        );

    }

}


/* 11. RESTART THE GAME */

function restartGame() {

    // Resets the game state
    currentQuestion = 0;
    score = 0;
    selectedAnswer = null;
    answered = false;

    // Hides the final screen
    resultScreen.hidden = true;

    // Displays the quiz again
    quizPanel.hidden = false;

    // Restarts the alien's dialogue
    guideTitle.textContent = "Hello, explorer!";

    // Clears the saved score
    try {

        localStorage.removeItem("quizScore");

    } catch (error) {

        console.warn(
            "Unable to clear the saved score.",
            error
        );

    }

    // Loads the first question
    showQuestion();

}


/* 12. BUTTON EVENTS */

// Submit the selected answer
submitButton.addEventListener("click", submitAnswer);

// Advance after viewing the feedback
nextButton.addEventListener("click", nextQuestion);

// Restart the quiz
restartButton.addEventListener("click", restartGame);


/* 13. INITIALIZATION */

if (elementsAreValid && questions.length > 0) {

    // Starts the quiz with the first question
    showQuestion();

} else {

    // Reports possible structural problems
    console.error(
        "Unable to start the quiz. Check the HTML elements and the question bank."
    );


}