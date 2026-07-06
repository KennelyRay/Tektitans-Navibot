$(document).ready(function() {
    console.log("Script loaded successfully!");
    let eventSource = null;

    // Initialize React component
    const root = ReactDOM.createRoot(document.getElementById('static-questions'));
    root.render(React.createElement(StaticQuestionsCarousel, {
        onQuestionSelect: handleStaticQuestion
    }));

    // Handle static question click
    function handleStaticQuestion(question) {
        appendMessage('user', question);
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
        eventSource = new EventSource('/chat-stream?message=' + encodeURIComponent(input));

        let accumulatedData = '';

        eventSource.onmessage = function(event) {
            if (event.data === '[END]') {
                eventSource.close();
                $('#send-btn').text("Send");
                $('#chat-box .message.bot').last().find('.typing-indicator-container').remove();
                return;
            }
            accumulatedData = event.data.replace(/:\s+/g, ':\n');
            $('#chat-box .message.bot').last().find('.message-content').html(accumulatedData);
            scrollChatToBottom();
        };

        eventSource.onerror = function() {
            eventSource.close();
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
        $('#chat-container').toggle();
    });

    $('#close-btn').click(function() {
        $('#chat-container').hide();
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
});