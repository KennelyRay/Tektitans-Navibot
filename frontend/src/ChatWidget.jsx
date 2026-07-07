import { useEffect, useRef, useState } from 'react';
import StaticQuestionsCarousel from './StaticQuestionsCarousel.jsx';

const MAX_HISTORY_TURNS = 6;

function normalizeMessageText(html) {
    const div = document.createElement('div');
    div.innerHTML = html;
    return (div.textContent || '').replace(/\s+/g, ' ').trim();
}

function makeMessageId() {
    return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export default function ChatWidget() {
    const [isOpen, setIsOpen] = useState(false);
    const [messages, setMessages] = useState([]);
    const [inputValue, setInputValue] = useState('');
    const [isSending, setIsSending] = useState(false);

    const historyRef = useRef([]);
    const eventSourceRef = useRef(null);
    const currentBotMessageIdRef = useRef(null);
    const chatBoxRef = useRef(null);
    const inputRef = useRef(null);

    useEffect(() => {
        const box = chatBoxRef.current;
        if (box) {
            box.scrollTop = box.scrollHeight;
        }
    }, [messages]);

    useEffect(() => {
        function handleKeyDown(event) {
            if (event.key === 'Escape' && isOpen) {
                setIsOpen(false);
            }
        }
        document.addEventListener('keydown', handleKeyDown);
        return () => document.removeEventListener('keydown', handleKeyDown);
    }, [isOpen]);

    useEffect(() => {
        return () => {
            if (eventSourceRef.current) {
                eventSourceRef.current.close();
            }
        };
    }, []);

    function openChat() {
        setIsOpen(true);
        window.setTimeout(() => inputRef.current && inputRef.current.focus(), 80);
    }

    function toggleChat() {
        setIsOpen((prev) => {
            const next = !prev;
            if (next) {
                window.setTimeout(() => inputRef.current && inputRef.current.focus(), 80);
            }
            return next;
        });
    }

    function addHistoryEntry(role, html) {
        const normalizedText = normalizeMessageText(html);
        if (!normalizedText) return;
        historyRef.current.push({ role, text: normalizedText });
        if (historyRef.current.length > MAX_HISTORY_TURNS) {
            historyRef.current.splice(0, historyRef.current.length - MAX_HISTORY_TURNS);
        }
    }

    function appendMessage(role, html, extra = {}) {
        const id = makeMessageId();
        setMessages((prev) => [...prev, { id, role, html, showTyping: false, ...extra }]);
        return id;
    }

    function processUserInput(input) {
        const botMessageId = appendMessage('bot', '', { showTyping: true });
        currentBotMessageIdRef.current = botMessageId;
        setIsSending(true);

        // The just-sent user turn is already excluded here since it's passed
        // separately as `message` - history is prior turns only.
        const historyPayload = encodeURIComponent(JSON.stringify(historyRef.current.slice(0, -1)));
        const eventSource = new EventSource(
            `/chat-stream?message=${encodeURIComponent(input)}&history=${historyPayload}`
        );
        eventSourceRef.current = eventSource;

        let accumulatedData = '';

        eventSource.onmessage = (event) => {
            if (event.data === '[END]') {
                eventSource.close();
                eventSourceRef.current = null;
                setIsSending(false);
                setMessages((prev) =>
                    prev.map((m) => (m.id === botMessageId ? { ...m, showTyping: false } : m))
                );
                addHistoryEntry('bot', accumulatedData);
                return;
            }
            // Swap the typing dots for the reply as soon as the first chunk arrives,
            // instead of leaving them showing next to text that's already streaming in.
            accumulatedData = event.data.replace(/:\s+/g, ':\n');
            setMessages((prev) =>
                prev.map((m) => (m.id === botMessageId ? { ...m, html: accumulatedData, showTyping: false } : m))
            );
        };

        eventSource.onerror = () => {
            eventSource.close();
            eventSourceRef.current = null;
            setIsSending(false);
            setMessages((prev) =>
                prev.map((m) =>
                    m.id === botMessageId
                        ? { ...m, showTyping: false, html: `${m.html}An error occurred.` }
                        : m
                )
            );
        };
    }

    function handleSend() {
        const trimmed = inputValue.trim();
        if (!trimmed || isSending) return;
        appendMessage('user', trimmed);
        addHistoryEntry('user', trimmed);
        setInputValue('');
        processUserInput(trimmed);
    }

    function handleCancel() {
        const eventSource = eventSourceRef.current;
        if (!eventSource) return;
        eventSource.close();
        eventSourceRef.current = null;
        setIsSending(false);
        const botMessageId = currentBotMessageIdRef.current;
        setMessages((prev) =>
            prev.map((m) =>
                m.id === botMessageId
                    ? { ...m, showTyping: false, html: `${m.html}Response canceled.` }
                    : m
            )
        );
    }

    function handleStaticQuestionSelect(question) {
        openChat();
        appendMessage('user', question);
        addHistoryEntry('user', question);
        processUserInput(question);
    }

    function handleSendButtonClick() {
        if (isSending) {
            handleCancel();
        } else {
            handleSend();
        }
    }

    function handleInputKeyDown(event) {
        if (event.key === 'Enter' && !isSending) {
            handleSend();
        }
    }

    function handleBubbleKeyDown(event) {
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            toggleChat();
        }
    }

    return (
        <>
            <div
                id="chat-bubble"
                aria-label="Open Navibot chat"
                role="button"
                tabIndex={0}
                onClick={toggleChat}
                onKeyDown={handleBubbleKeyDown}
            >
                <span className="chat-bubble-ring" />
                <img src="/static/images/chatbot_icon.png" alt="Robot Icon" />
                <span className="chat-bubble-status" />
            </div>

            <div id="chat-container" className={isOpen ? 'show' : ''}>
                <div id="chat-header">
                    <div className="chat-header-profile">
                        <div className="chat-header-avatar">
                            <img src="/static/images/chatbot_icon.png" alt="Robot Icon" />
                        </div>
                        <div className="chat-header-copy">
                            <span className="chat-header-title">Navibot</span>
                            <span className="chat-header-subtitle">Enrollment Assistant</span>
                        </div>
                    </div>
                    <div className="chat-header-actions">
                        <div className="chat-help">
                            <button id="help-btn" type="button" aria-label="Show Navibot disclaimer">
                                ?
                            </button>
                            <div className="chat-help-tooltip" role="tooltip">
                                Please note: Navibot is designed to help with enrollment FAQs, the information
                                provided may not always be fully accurate or up-to-date. For important details,
                                please verify with official school resources.
                            </div>
                        </div>
                        <button id="close-btn" onClick={() => setIsOpen(false)}>
                            &times;
                        </button>
                    </div>
                </div>

                <div id="chat-box" ref={chatBoxRef}>
                    <div className="message-container bot intro-message">
                        <div className="avatar" />
                        <div className="message bot intro-card">
                            <div className="intro-badge">Online</div>
                            <div className="message-content">
                                <p>Hello! I’m Navibot.</p>
                                <p>
                                    I can help with enrollment questions, schedules, requirements, and other
                                    student portal guidance.
                                </p>
                            </div>
                            <div className="message-meta">Ask a question or tap a suggested prompt below.</div>
                        </div>
                    </div>

                    {messages.map((message) => (
                        <div key={message.id} className={`message-container ${message.role}`}>
                            {message.role === 'bot' && <div className="avatar" />}
                            <div className={`message ${message.role}`}>
                                {message.role === 'bot' ? (
                                    <>
                                        <div
                                            className="message-content"
                                            dangerouslySetInnerHTML={{ __html: message.html }}
                                        />
                                        {message.showTyping && (
                                            <div className="typing-indicator-container">
                                                <span className="typing-indicator" />
                                                <span className="typing-indicator" />
                                                <span className="typing-indicator" />
                                            </div>
                                        )}
                                    </>
                                ) : (
                                    message.html
                                )}
                            </div>
                            {message.role === 'user' && <div className="avatar" />}
                        </div>
                    ))}
                </div>

                <div id="static-questions">
                    <StaticQuestionsCarousel onQuestionSelect={handleStaticQuestionSelect} />
                </div>

                <div id="input-container">
                    <input
                        type="text"
                        id="user-input"
                        placeholder="Type your message..."
                        value={inputValue}
                        onChange={(event) => setInputValue(event.target.value)}
                        onKeyDown={handleInputKeyDown}
                        ref={inputRef}
                    />
                    <button id="send-btn" onClick={handleSendButtonClick}>
                        {isSending ? 'Cancel' : 'Send'}
                    </button>
                </div>
            </div>
        </>
    );
}
