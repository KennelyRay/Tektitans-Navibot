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

    const navigationButtonStyle = {
        width: '36px',
        height: '36px',
        borderRadius: '12px',
        border: '1px solid rgba(11, 45, 99, 0.1)',
        backgroundColor: '#ffffff',
        color: '#0b2d63',
        fontSize: '16px',
        cursor: 'pointer',
        boxShadow: '0 10px 20px rgba(11, 45, 99, 0.08)',
        flexShrink: 0,
    };

    const questionButtonStyle = {
        width: '100%',
        padding: '10px 12px',
        borderRadius: '16px',
        border: '1px solid rgba(11, 45, 99, 0.08)',
        backgroundColor: '#ffffff',
        color: '#173056',
        textAlign: 'left',
        fontSize: '12px',
        fontWeight: '600',
        lineHeight: '1.45',
        transition: 'transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease',
        boxShadow: '0 10px 18px rgba(11, 45, 99, 0.05)',
    };

    return React.createElement(
        'div',
        {
            style: {
                width: '100%',
                display: 'flex',
                alignItems: 'center',
                gap: '10px'
            }
        },
        [
            React.createElement(
                'button',
                {
                    onClick: handlePrev,
                    key: 'prev',
                    style: navigationButtonStyle,
                    'aria-label': 'Previous suggested questions',
                    disabled: staticQuestions.length === 0
                },
                '←'
            ),
            React.createElement(
                'div',
                {
                    key: 'questions',
                    style: {
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '8px',
                        width: '100%'
                    }
                },
                visibleQuestions.length
                    ? visibleQuestions.map((question, index) =>
                        React.createElement(
                            'button',
                            {
                                key: `${question}-${index}`,
                                onClick: () => onQuestionSelect(question),
                                style: questionButtonStyle,
                                onMouseEnter: (e) => {
                                    e.currentTarget.style.transform = 'translateY(-1px)';
                                    e.currentTarget.style.boxShadow = '0 14px 22px rgba(11, 45, 99, 0.1)';
                                    e.currentTarget.style.borderColor = 'rgba(11, 45, 99, 0.18)';
                                },
                                onMouseLeave: (e) => {
                                    e.currentTarget.style.transform = 'translateY(0)';
                                    e.currentTarget.style.boxShadow = '0 10px 18px rgba(11, 45, 99, 0.05)';
                                    e.currentTarget.style.borderColor = 'rgba(11, 45, 99, 0.08)';
                                }
                            },
                            question
                        )
                    )
                    : React.createElement(
                        'div',
                        {
                            style: {
                                padding: '12px 14px',
                                borderRadius: '16px',
                                backgroundColor: 'rgba(11, 45, 99, 0.04)',
                                color: '#62718b',
                                fontSize: '12px',
                                textAlign: 'center'
                            }
                        },
                        'Suggested questions will appear here.'
                    )
            ),
            React.createElement(
                'button',
                {
                    onClick: handleNext,
                    key: 'next',
                    style: navigationButtonStyle,
                    'aria-label': 'Next suggested questions',
                    disabled: staticQuestions.length === 0
                },
                '→'
            )
        ]
    );
};
