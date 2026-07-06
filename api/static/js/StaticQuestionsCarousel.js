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
    const totalPages = Math.ceil(staticQuestions.length / itemsPerPage);

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

    return React.createElement(
        'div',
        {
            className: 'bg-white',
            style: {
                minHeight: '75px',
                display: 'flex',
                flexDirection: 'row',
                alignItems: 'center',
                justifyContent: 'space-between',
                position: 'relative',
                width: '350px'
            }
        },
        [
            React.createElement(
                'button',
                {
                    onClick: handlePrev,
                    className: 'w-8 h-full flex items-center justify-center',
                    key: 'prev',
                    style: {
                        color: '#012a57',
                        fontSize: '18px',
                        border: '1px solid white',
                        backgroundColor: 'white'
                    }
                },
                '←'
            ),
            React.createElement(
                'div',
                {
                    className: 'flex-1',
                    key: 'questions',
                    style: {
                        display: 'flex',
                        flexDirection: 'column',
                        height: '100%',
                        width: '100%',
                    }
                },
                React.createElement(
                    'div',
                    {
                        className: 'flex flex-col gap-3',
                        style: {
                            display: 'flex',
                            flexDirection: 'column',
                            justifyContent: 'center',
                            alignItems: 'center',
                            height: '100%'
                        }
                    },
                    visibleQuestions.map((question, index) =>
                        React.createElement(
                            'button',
                            {
                                key: index,
                                onClick: () => onQuestionSelect(question),
                                style: {
                                    borderRadius: '10px',
                                    border: '1px solid #e2e8f0',
                                    padding: '6px 8px',
                                    textAlign: 'center',
                                    fontSize: '11px',
                                    backgroundColor: 'white',
                                    transition: 'all 0.2s ease',
                                    width: '100%',
                                    maxWidth: '300px',
                                    marginBottom: '1px'
                                },
                                onMouseEnter: (e) => {
                                    e.currentTarget.style.backgroundColor = '#f8fafc';
                                    e.currentTarget.style.transform = 'translateY(-1px)';
                                    e.currentTarget.style.boxShadow = '0 2px 4px rgba(0, 0, 0, 0.1)';
                                },
                                onMouseLeave: (e) => {
                                    e.currentTarget.style.backgroundColor = 'white';
                                    e.currentTarget.style.transform = 'translateY(0)';
                                    e.currentTarget.style.boxShadow = '0 1px 2px rgba(0, 0, 0, 0.05)';
                                }
                            },
                            question
                        )
                    )
                )
            ),
            React.createElement(
                'button',
                {
                    onClick: handleNext,
                    className: 'w-8 h-full flex items-center justify-center',
                    key: 'next',
                    style: {
                        color: '#012a57',
                        fontSize: '18px',
                        border: '1px solid white',
                        backgroundColor: 'white',
                    }
                },
                '→'
            )
        ]
    );
};