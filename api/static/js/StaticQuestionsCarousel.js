// StaticQuestionsCarousel.js
const MAX_SUGGESTED_QUESTIONS = 6;

const StaticQuestionsCarousel = ({ onQuestionSelect }) => {
    const [staticQuestions, setStaticQuestions] = React.useState([]);

    React.useEffect(() => {
        const loadQuestions = async () => {
            try {
                const response = await fetch('/Data/static_qa.json');  // Match the route in Flask
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                const qaData = await response.json();
                // The FAQ dataset keeps growing as the bot is trained with more answers,
                // but the suggested-prompts row only surfaces the first few; the
                // rest stay answerable by typing, they're just not shown as quick-tap chips.
                setStaticQuestions(Object.keys(qaData).slice(0, MAX_SUGGESTED_QUESTIONS));
            } catch (error) {
                console.error('Error loading questions:', error);
                setStaticQuestions([]);
            }
        };

        loadQuestions();
    }, []);

    if (!staticQuestions.length) {
        return React.createElement(
            'div',
            { className: 'suggested-prompts-empty' },
            'Suggested questions will appear here.'
        );
    }

    // Messenger-style quick replies: a single horizontally scrollable row of
    // pill chips, tap one to send it. No pagination arrows or page dots.
    return React.createElement(
        'div',
        {
            className: 'suggested-prompts-row',
            role: 'list',
            'aria-label': 'Suggested prompts'
        },
        staticQuestions.map((question, index) =>
            React.createElement(
                'button',
                {
                    key: `${question}-${index}`,
                    role: 'listitem',
                    onClick: () => onQuestionSelect(question),
                    className: 'suggested-prompt-chip'
                },
                question
            )
        )
    );
};
