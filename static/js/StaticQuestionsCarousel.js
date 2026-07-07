// StaticQuestionsCarousel.js
const MAX_SUGGESTED_QUESTIONS = 6;
const SCROLL_STEP_PX = 180;

const StaticQuestionsCarousel = ({ onQuestionSelect }) => {
    const [staticQuestions, setStaticQuestions] = React.useState([]);
    const [canScrollPrev, setCanScrollPrev] = React.useState(false);
    const [canScrollNext, setCanScrollNext] = React.useState(false);
    const rowRef = React.useRef(null);

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

    const updateScrollState = React.useCallback(() => {
        const row = rowRef.current;
        if (!row) return;
        setCanScrollPrev(row.scrollLeft > 4);
        setCanScrollNext(row.scrollLeft < row.scrollWidth - row.clientWidth - 4);
    }, []);

    React.useEffect(() => {
        updateScrollState();
    }, [staticQuestions, updateScrollState]);

    React.useEffect(() => {
        const row = rowRef.current;
        // The chat widget is `display: none` until the user opens it, so the row
        // measures 0-width (and both arrows look permanently disabled) if we only
        // check bounds once on mount. A ResizeObserver re-checks as soon as the
        // row actually gets laid out with real dimensions (e.g. when the chat
        // window opens), and again on any later resize.
        if (!row || typeof ResizeObserver === 'undefined') {
            return undefined;
        }
        const observer = new ResizeObserver(() => updateScrollState());
        observer.observe(row);
        return () => observer.disconnect();
    }, [staticQuestions, updateScrollState]);

    const scrollByStep = (direction) => {
        const row = rowRef.current;
        if (!row) return;
        row.scrollBy({ left: direction * SCROLL_STEP_PX, behavior: 'smooth' });
        // The scroll animates asynchronously, so re-check the bounds shortly after
        // instead of only relying on the (no-drag) row's own scroll event.
        window.setTimeout(updateScrollState, 260);
    };

    if (!staticQuestions.length) {
        return React.createElement(
            'div',
            { className: 'suggested-prompts-empty' },
            'Suggested questions will appear here.'
        );
    }

    // Messenger-style quick reply chips, but paged with explicit prev/next
    // arrows instead of free swipe/drag scrolling.
    return React.createElement(
        'div',
        { className: 'suggested-prompts-shell' },
        [
            React.createElement(
                'button',
                {
                    key: 'prev',
                    type: 'button',
                    onClick: () => scrollByStep(-1),
                    className: 'suggested-prompts-nav',
                    'aria-label': 'Show previous suggested prompts',
                    disabled: !canScrollPrev
                },
                '←'
            ),
            React.createElement(
                'div',
                {
                    key: 'row',
                    ref: rowRef,
                    className: 'suggested-prompts-row',
                    role: 'list',
                    'aria-label': 'Suggested prompts',
                    onScroll: updateScrollState
                },
                staticQuestions.map((question, index) =>
                    React.createElement(
                        'button',
                        {
                            key: `${question}-${index}`,
                            type: 'button',
                            role: 'listitem',
                            onClick: () => onQuestionSelect(question),
                            className: 'suggested-prompt-chip'
                        },
                        question
                    )
                )
            ),
            React.createElement(
                'button',
                {
                    key: 'next',
                    type: 'button',
                    onClick: () => scrollByStep(1),
                    className: 'suggested-prompts-nav',
                    'aria-label': 'Show more suggested prompts',
                    disabled: !canScrollNext
                },
                '→'
            )
        ]
    );
};
