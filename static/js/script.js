$(document).ready(function() {
    let eventSource = null;
    const conversationHistory = [];
    const $chatContainer = $('#chat-container');
    const $chatInput = $('#user-input');
    $('#chat-container').removeClass('show');

    function openChat() {
        $chatContainer.addClass('show');
        window.setTimeout(() => $chatInput.trigger('focus'), 80);
    }

    function closeChat() {
        $chatContainer.removeClass('show');
    }

    function normalizeMessageText(content) {
        return $('<div>').html(content).text().replace(/\s+/g, ' ').trim();
    }

    function addHistoryEntry(role, text) {
        const normalizedText = normalizeMessageText(text);
        if (!normalizedText) return;
        conversationHistory.push({ role, text: normalizedText });
        if (conversationHistory.length > 6) {
            conversationHistory.splice(0, conversationHistory.length - 6);
        }
    }

    // Initialize React component
    const root = ReactDOM.createRoot(document.getElementById('static-questions'));
    root.render(React.createElement(StaticQuestionsCarousel, {
        onQuestionSelect: handleStaticQuestion
    }));

    // Handle static question click
    function handleStaticQuestion(question) {
        openChat();
        appendMessage('user', question);
        addHistoryEntry('user', question);
        processUserInput(question);
    }

    function appendMessage(type, content) {
        const messageHtml = type === 'user'
            ? `<div class="message-container user">
                <div class="message user">${content}</div>
                <div class="avatar"></div>
               </div>`
            : `<div class="message-container bot">
                <div class="avatar"></div>
                <div class="message bot">
                    <div class="message-content">${content}</div>
                </div>
               </div>`;

        $('#chat-box').append(messageHtml);
    }

    // Process user input (either from text input or carousel)
    function processUserInput(input) {
        // Add bot response container with typing indicator
        $('#chat-box').append(
            `<div class="message-container bot">
                <div class="avatar"></div>
                <div class="message bot">
                    <div class="message-content"></div>
                    <div class="typing-indicator-container">
                        <span class="typing-indicator"></span>
                        <span class="typing-indicator"></span>
                        <span class="typing-indicator"></span>
                    </div>
                </div>
            </div>`
        );
        scrollChatToBottom();

        $('#send-btn').text("Cancel");

        // Send to backend for processing
        const historyPayload = encodeURIComponent(JSON.stringify(conversationHistory.slice(0, -1)));
        eventSource = new EventSource('/chat-stream?message=' + encodeURIComponent(input) + '&history=' + historyPayload);

        let accumulatedData = '';

        eventSource.onmessage = function(event) {
            if (event.data === '[END]') {
                eventSource.close();
                eventSource = null;
                $('#send-btn').text("Send");
                $('#chat-box .message.bot').last().find('.typing-indicator-container').remove();
                addHistoryEntry('bot', accumulatedData);
                return;
            }
            accumulatedData = event.data.replace(/:\s+/g, ':\n');
            $('#chat-box .message.bot').last().find('.message-content').html(accumulatedData);
            scrollChatToBottom();
        };

        eventSource.onerror = function() {
            eventSource.close();
            eventSource = null;
            $('#send-btn').text("Send");
            $('#chat-box .message.bot').last().find('.typing-indicator-container').remove();
            $('#chat-box .message.bot').last().find('.message-content').append('An error occurred.');
            scrollChatToBottom();
        };
    }

    // Send message
    function sendMessage() {
        const userInput = $('#user-input').val().trim();
        if (!userInput) return;

        appendMessage('user', userInput);
        addHistoryEntry('user', userInput);
        $('#user-input').val('');
        scrollChatToBottom();

        processUserInput(userInput);
    }

    function cancelMessage() {
        if (eventSource) {
            eventSource.close();
            eventSource = null;
            $('#chat-box .message.bot').last().find('.typing-indicator-container').remove();
            $('#chat-box .message.bot').last().find('.message-content').append('Response canceled.');
            $('#send-btn').text("Send");
            scrollChatToBottom();
        }
    }

    function scrollChatToBottom() {
        $('#chat-box').scrollTop($('#chat-box')[0].scrollHeight);
    }

    // Event listeners
    $('#sidebar-toggle').click(function() {
        $('#sidebar').toggleClass('open');
    });

    $('#chat-bubble').click(function() {
        if ($chatContainer.hasClass('show')) {
            closeChat();
        } else {
            openChat();
        }
    });

    $('#close-btn').click(function() {
        closeChat();
    });

    $('#chat-bubble').keypress(function(event) {
        if (event.which === 13 || event.which === 32) {
            event.preventDefault();
            if ($chatContainer.hasClass('show')) {
                closeChat();
            } else {
                openChat();
            }
        }
    });

    $('#send-btn').click(function() {
        if ($(this).text() === "Send") {
            sendMessage();
        } else {
            cancelMessage();
        }
    });

    $('#user-input').keypress(function(event) {
        if (event.which === 13 && $('#send-btn').text() === "Send") {
            sendMessage();
        }
    });

    $(document).keydown(function(event) {
        if (event.key === 'Escape' && $chatContainer.hasClass('show')) {
            closeChat();
        }
    });
});
