// StaticQuestionsCarousel.js
const StaticQuestionsCarousel = ({ onQuestionSelect }) => {
    const [activeIndex, setActiveIndex] = React.useState(0);
    const [staticQuestions, setStaticQuestions] = React.useState([]);

    React.useEffect(() => {
        const loadQuestions = async () => {
            try {
                const response = await fetch('/Data/static_qa.json');  // Match the route in Flask
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                const qaData = await response.json();
                setStaticQuestions(Object.keys(qaData));
            } catch (error) {
                console.error('Error loading questions:', error);
                setStaticQuestions([]);
            }
        };

        loadQuestions();
    }, []);

    const itemsPerPage = 2;
    const totalPages = Math.max(1, Math.ceil(staticQuestions.length / itemsPerPage));

    const handleNext = () => {
        setActiveIndex((prev) => (prev + 1) % totalPages);
    };

    const handlePrev = () => {
        setActiveIndex((prev) => (prev - 1 + totalPages) % totalPages);
    };

    const visibleQuestions = staticQuestions.slice(
        activeIndex * itemsPerPage,
        (activeIndex + 1) * itemsPerPage
    );

    const promptIndicatorDots = Array.from({ length: totalPages }, (_, index) =>
        React.createElement('span', {
            key: `prompt-dot-${index}`,
            className: `suggested-prompts-dot${index === activeIndex ? ' active' : ''}`
        })
    );

    return React.createElement(
        'div',
        {
            className: 'suggested-prompts-shell'
        },
        [
            React.createElement(
                'div',
                {
                    key: 'header',
                    className: 'suggested-prompts-header'
                },
                [
                    React.createElement(
                        'div',
                        {
                            key: 'copy',
                            className: 'suggested-prompts-copy'
                        },
                        [
                            React.createElement(
                                'div',
                                {
                                    key: 'label',
                                    className: 'suggested-prompts-label'
                                },
                                'Suggested Prompts'
                            ),
                            React.createElement(
                                'div',
                                {
                                    key: 'hint',
                                    className: 'suggested-prompts-hint'
                                },
                                'Try one of these common questions.'
                            )
                        ]
                    ),
                    React.createElement(
                        'div',
                        {
                            key: 'pager',
                            className: 'suggested-prompts-pager',
                            'aria-label': 'Suggested prompt pages'
                        },
                        promptIndicatorDots
                    )
                ]
            ),
            React.createElement(
                'div',
                {
                    key: 'body',
                    className: 'suggested-prompts-body'
                },
                [
                    React.createElement(
                        'button',
                        {
                            onClick: handlePrev,
                            key: 'prev',
                            className: 'suggested-prompts-nav',
                            'aria-label': 'Previous suggested questions',
                            disabled: staticQuestions.length === 0
                        },
                        '\u2190'
                    ),
                    React.createElement(
                        'div',
                        {
                            key: 'questions',
                            className: 'suggested-prompts-list'
                        },
                        visibleQuestions.length
                            ? visibleQuestions.map((question, index) =>
                                React.createElement(
                                    'button',
                                    {
                                        key: `${question}-${index}`,
                                        onClick: () => onQuestionSelect(question),
                                        className: 'suggested-prompt-card'
                                    },
                                    [
                                        React.createElement(
                                            'span',
                                            {
                                                key: 'badge',
                                                className: 'suggested-prompt-badge'
                                            },
                                            'Ask'
                                        ),
                                        React.createElement(
                                            'span',
                                            {
                                                key: 'text',
                                                className: 'suggested-prompt-text'
                                            },
                                            question
                                        )
                                    ]
                                )
                            )
                            : React.createElement(
                                'div',
                                {
                                    className: 'suggested-prompts-empty'
                                },
                                'Suggested questions will appear here.'
                            )
                    ),
                    React.createElement(
                        'button',
                        {
                            onClick: handleNext,
                            key: 'next',
                            className: 'suggested-prompts-nav',
                            'aria-label': 'Next suggested questions',
                            disabled: staticQuestions.length === 0
                        },
                        '\u2192'
                    )
                ]
            )
        ]
    );
};
