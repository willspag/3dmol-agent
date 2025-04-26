/**
 * AI Chat Assistant for 3D Molecular Viewer
 * Handles communication with the OpenAI-powered backend and
 * renders chat messages and function calls in the UI.
 * This version uses REST API for more reliable communication.
 */
class ChatAssistant {
    constructor(socket) {
        // Keep socket for backward compatibility, but we'll use fetch for chat
        this.socket = socket;
        this.chatMessages = document.getElementById('chat-messages');
        this.chatForm = document.getElementById('chat-form');
        this.chatInput = document.getElementById('chat-input');
        this.clearChatBtn = document.getElementById('clear-chat-btn');
        this.assistantStatus = document.getElementById('assistant-status');
        
        this.isProcessing = false;
        this.currentAssistantMessage = null;
        
        // API endpoint for our chat
        this.apiEndpoint = '/api/chat';
        
        this.initEvents();
        
    }
    
    initEvents() {
        // Handle chat form submission
        this.chatForm.addEventListener('submit', (e) => {
            e.preventDefault();
            this.sendMessage();
        });
        
        // Handle clearing chat
        this.clearChatBtn.addEventListener('click', () => {
            this.clearChat();
        });
        
        // For backward compatibility - still listen for Socket.IO responses
        this.socket.on('ai_response', (data) => {
            console.log('Received legacy Socket.IO response:', data);
            this.handleAIResponse(data);
        });
    }
    
    async sendMessage() {
        const message = this.chatInput.value.trim();
        if (!message || this.isProcessing) return;
        
        // Add user message to chat
        this.addUserMessage(message);
        
        // Clear input and disable until response is complete
        this.chatInput.value = '';
        this.setProcessingState(true);
        
        // Add typing indicator
        this.addTypingIndicator();
        
        try {
            // Send message to server using fetch API (more reliable than Socket.IO)
            console.log("Sending message to API:", message);
            const response = await fetch(this.apiEndpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ message }),
            });
            
            if (!response.ok) {
                throw new Error(`API error: ${response.status} ${response.statusText}`);
            }
            
            const data = await response.json();
            console.log("Received API response:", data);
            
            // Remove typing indicator
            this.removeTypingIndicator();
            
            // Process each response in sequence
            if (data.responses && data.responses.length > 0) {
                data.responses.forEach(item => {
                    this.handleAIResponse(item);
                });
            } else if (data.error) {
                this.handleError(data.error);
            }
        } catch (error) {
            console.error("Error sending message to API:", error);
            this.removeTypingIndicator();
            this.handleError(`Error: ${error.message}`);
        } finally {
            this.setProcessingState(false);
        }
    }
    
    handleAIResponse(data) {
        if (data.type === 'text') {
            // Send full data object, not just dataa.content in order to also handle annotations (if any)
            this.handleTextResponse(data);
        } else if (data.type === 'tool_start') {
            this.handleToolStart(data.name, data.arguments);
        } else if (data.type === 'tool_result') {
            this.handleToolResult(data.name, data.result);
        } else if (data.type === 'tool_error') {
            this.handleToolError(data.name, data.error);
        } else if (data.type === 'reasoning') {
            this.addReasoningSummary(data.content);
        } else if (data.type === 'web_search_call') {
            this.handleWebSearchCall(data.status);
        } else if (data.type === 'error') {
            this.handleError(data.content);
        }
        
        // Scroll chat to bottom
        this.scrollToBottom();
    }
    
    handleTextResponse(data) {
        const content = data.content;
        const annotations = data.annotations;

        // Ensure the main message container exists
        if (!this.currentAssistantMessage) {
            this.currentAssistantMessage = this.createMessageElement('assistant');
            this.chatMessages.appendChild(this.currentAssistantMessage);

            // Add the primary content container
            const messageContent = document.createElement('div');
            messageContent.className = 'message-content';
            this.currentAssistantMessage.appendChild(messageContent);
        }

        // Append new content to the message content container
        const messageContent = this.currentAssistantMessage.querySelector('.message-content');
        // Append formatted new content - handles streaming better than re-formatting all text
        messageContent.innerHTML += this.formatMarkdown(content);

        // Handle annotations if they exist
        if (annotations && annotations.length > 0) {
            // Find or create the annotations container
            let annotationsContainer = this.currentAssistantMessage.querySelector('.annotations-container');
            if (!annotationsContainer) {
                annotationsContainer = document.createElement('div');
                annotationsContainer.className = 'annotations-container';
                // Insert after the message content
                messageContent.insertAdjacentElement('afterend', annotationsContainer);
            }

            // Clear previous annotations from this specific container (if any)
            // This assumes annotations might be sent incrementally or updated
            // annotationsContainer.innerHTML = ''; // Let's append for now, might need clearing logic if backend sends duplicates

            const annotationsList = document.createElement('ul');
            annotationsList.className = 'annotations-list';

            annotations.forEach((annotation, index) => {
                if (annotation.type === 'url_citation' && annotation.url && annotation.title) {
                    const listItem = document.createElement('li');

                    const link = document.createElement('a');
                    link.href = annotation.url;
                    link.textContent = annotation.title;
                    link.target = '_blank'; // Open in new tab
                    link.rel = 'noopener noreferrer'; // Security best practice
                    link.className = 'annotation-link';

                    // Add a small citation number/marker
                    const citationMarker = document.createElement('span');
                    citationMarker.className = 'citation-marker';
                    // You might want a more robust way to number citations if they relate to specific text parts
                    citationMarker.textContent = `[${index + 1}]`; 

                    listItem.appendChild(citationMarker);
                    listItem.appendChild(link);
                    annotationsList.appendChild(listItem);
                }
            });
            
            // Only append the list if it contains items
            if (annotationsList.hasChildNodes()) {
                 // Clear existing list before appending new one to prevent duplicates if function is called multiple times with same annotations
                 const existingList = annotationsContainer.querySelector('.annotations-list');
                 if (existingList) {
                     existingList.remove();
                 }
                annotationsContainer.appendChild(annotationsList);
            }
        }

        // Set status to normal after receiving text
        this.setProcessingState(false);
    }
    
    async handleToolStart(name, args) {
        // Get global viewer instance
        const molecularViewer = window.molecularViewer;
        if (!molecularViewer) {
            console.error("Cannot find molecular viewer instance");
            return;
        }
        
        // Create a tool message
        const toolMessage = document.createElement('div');
        toolMessage.className = 'tool-message';
        
        // Format the message based on the tool name
        let actionText = '';
        switch (name) {
            case 'load_pdb':
                actionText = `Loading PDB structure: ${args.pdb_id}`;
                break;
            case 'highlight_hetero':
                actionText = 'Highlighting hetero atoms in the structure';
                break;
            case 'show_surface':
                actionText = 'Showing surface representation';
                break;
            case 'rotate':
                const x = args.x || 0;
                const y = args.y || 0;
                const z = args.z || 0;
                actionText = `Rotating view: X=${x}°, Y=${y}°, Z=${z}°`;
                break;
            case 'zoom':
                actionText = `Zooming view by factor: ${args.factor}`;
                break;
            case 'add_box':
                actionText = 'Adding box around region';
                break;
            case 'set_style':
                actionText = 'Setting custom visual style';
                break;
            case 'reset_view':
                actionText = 'Resetting view to default';
                break;
            default:
                actionText = `Executing function: ${name}`;
        }
        
        toolMessage.textContent = `🔄 ${actionText}...`;
        this.chatMessages.appendChild(toolMessage);
        
        // Reset the current assistant message to allow new text after the tool call
        this.currentAssistantMessage = null;
        
        // Actually execute the viewer function directly in the browser
        // This is crucial - we're bypassing the backend for viewer manipulations
        try {
            console.log(`Attempting to handleToolStart with args: ${args}`);
            // Parse the incoming JSON arguments string into an object
            const parsedArgs = JSON.parse(args);
            let imageData = null;
            console.log(`Directly executing viewer function: ${name}`);
            
            switch (name) {
                case 'load_pdb':
                    console.log(`Calling moleculeViewer.loadPdb with parsedArgs.pdb_id=${parsedArgs.pdb_id}`)
                    imageData = await molecularViewer.loadPdb(parsedArgs.pdb_id);
                    break;
                case 'highlight_hetero':
                    imageData = await molecularViewer.highlightHetero();
                    break;
                case 'show_surface':
                    imageData = await molecularViewer.showSurface(parsedArgs.selection || {});
                    break;
                case 'rotate':
                    imageData = await molecularViewer.rotate(parsedArgs.x, parsedArgs.y, parsedArgs.z);
                    break;
                case 'zoom':
                    imageData = await molecularViewer.zoom(parsedArgs.factor);
                    break;
                case 'add_box':
                    imageData = await molecularViewer.addBox(parsedArgs.center, parsedArgs.size);
                    break;
                case 'set_style':
                    imageData = await molecularViewer.setStyle(parsedArgs.selection, parsedArgs.style);
                    break;
                case 'reset_view':
                    imageData = await molecularViewer.resetView();
                    break;
                default:
                    console.warn(`Unknown viewer function: ${name}`);
            }
            
            // Generate a better result with the actual image from the viewer
            this.handleToolResult(name, {
                success: true,
                message: actionText + " completed successfully",
                image: imageData ? imageData.split(',')[1] : null // extract base64 part
            });
            
        } catch (error) {
            console.error(`Error executing viewer function ${name}:`, error);
            this.handleToolResult(name, {
                success: false,
                message: `Error: ${error.message}`
            });
        }
    }
    
    handleToolResult(name, result) {
        // Find the tool message and update it
        const toolMessages = document.querySelectorAll('.tool-message');
        const toolMessage = toolMessages[toolMessages.length - 1];
        
        if (toolMessage) {
            // Clear existing content
            toolMessage.innerHTML = '';
            
            if (result.success) {
                // Create text message
                const messageText = document.createElement('div');
                messageText.textContent = `✅ ${result.message || 'Operation completed successfully'}`;
                toolMessage.appendChild(messageText);
                
                // Add image if available
                if (result.image) {
                    const imageContainer = document.createElement('div');
                    imageContainer.className = 'tool-image-container';
                    
                    const image = document.createElement('img');
                    image.src = `data:image/png;base64,${result.image}`;
                    image.className = 'tool-result-image';
                    image.alt = `Result of ${name}`;
                    
                    // Make the image clickable to view at full size
                    image.addEventListener('click', (e) => {
                        // Create modal or use existing Bootstrap modal
                        const modal = document.getElementById('imageModal');
                        const modalImage = document.getElementById('modalImage');
                        
                        if (modal && modalImage) {
                            modalImage.src = image.src;
                            const bsModal = new bootstrap.Modal(modal);
                            bsModal.show();
                        } else {
                            // Open in a new tab if modal doesn't exist
                            window.open(image.src, '_blank');
                        }
                    });
                    
                    imageContainer.appendChild(image);
                    toolMessage.appendChild(imageContainer);
                }
            } else {
                toolMessage.textContent = `❌ ${result.message || 'Operation failed'}`;
                toolMessage.classList.add('tool-error');
            }
        }
    }
    
    handleToolError(name, error) {
        // Find the tool message and update it
        const toolMessages = document.querySelectorAll('.tool-message');
        const toolMessage = toolMessages[toolMessages.length - 1];
        
        if (toolMessage) {
            toolMessage.textContent = `❌ Error: ${error}`;
            toolMessage.classList.add('tool-error');
        }
        
        // Set status back to normal
        this.setProcessingState(false);
    }
    
    handleError(content) {
        // Create an error message
        const errorMessage = document.createElement('div');
        errorMessage.className = 'message system';
        
        const messageContent = document.createElement('div');
        messageContent.className = 'message-content';
        messageContent.innerHTML = `<p>❌ ${content}</p>`;
        
        errorMessage.appendChild(messageContent);
        this.chatMessages.appendChild(errorMessage);
        
        // Set status back to normal
        this.setProcessingState(false);
    }
    
    addUserMessage(message) {
        const messageElement = this.createMessageElement('user');
        
        const messageContent = document.createElement('div');
        messageContent.className = 'message-content';
        messageContent.textContent = message;
        
        messageElement.appendChild(messageContent);
        this.chatMessages.appendChild(messageElement);
        
        // Reset current assistant message
        this.currentAssistantMessage = null;
        
        // Scroll to the bottom of the chat
        this.scrollToBottom();
    }
    
    addSystemMessage(message) {
        const messageElement = this.createMessageElement('system');
        
        const messageContent = document.createElement('div');
        messageContent.className = 'message-content';
        messageContent.innerHTML = `<p>${message}</p>`;
        
        messageElement.appendChild(messageContent);
        this.chatMessages.appendChild(messageElement);
        
        // Scroll to the bottom of the chat
        this.scrollToBottom();
    }
    
    createMessageElement(type) {
        const messageElement = document.createElement('div');
        messageElement.className = `message ${type}`;
        return messageElement;
    }
    
    addTypingIndicator() {
        const typingIndicator = document.createElement('div');
        typingIndicator.className = 'message assistant';
        typingIndicator.id = 'typing-indicator';
        
        const indicatorContent = document.createElement('div');
        indicatorContent.className = 'message-content';
        indicatorContent.innerHTML = `
            <div class="typing-indicator">
                <span></span>
                <span></span>
                <span></span>
            </div>
        `;
        
        typingIndicator.appendChild(indicatorContent);
        this.chatMessages.appendChild(typingIndicator);
        
        // Scroll to the bottom of the chat
        this.scrollToBottom();
    }
    
    removeTypingIndicator() {
        const typingIndicator = document.getElementById('typing-indicator');
        if (typingIndicator) {
            typingIndicator.remove();
        }
    }
    
    clearChat() {
        // Preserve the welcome message
        const welcomeContent = `<p>Hello! I'm your molecular biology assistant. I can help you visualize and manipulate protein structures. Ask me to load a PDB structure, rotate the view, highlight specific parts, or anything else related to 3D molecular visualization.</p>`;
        
        // Clear all messages on the frontend
        this.chatMessages.innerHTML = '';
        
        // Add a new welcome message
        const welcomeMessage = document.createElement('div');
        welcomeMessage.className = 'message system';
        
        const messageContent = document.createElement('div');
        messageContent.className = 'message-content';
        messageContent.innerHTML = welcomeContent;
        
        welcomeMessage.appendChild(messageContent);
        this.chatMessages.appendChild(welcomeMessage);

        // Call the backend to clear the conversation history
        fetch('/api/clear_chat_history', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                console.log('Chat history cleared on the server.');
            } else {
                console.error('Error clearing chat history on the server:', data.message);
                // Optionally display an error to the user
                this.addMessage('system', `Error clearing server history: ${data.message}`);
            }
        })
        .catch(error => {
            console.error('Failed to call clear chat history API:', error);
            // Optionally display an error to the user
            this.addMessage('system', `Failed to contact server to clear history: ${error}`);
        });
        
        // Reset state
        this.currentAssistantMessage = null;
        this.setProcessingState(false);
    }
    
    scrollToBottom() {
        const chatContainer = document.getElementById('chat-container');
        chatContainer.scrollTop = chatContainer.scrollHeight;
    }
    
    setProcessingState(isProcessing) {
        this.isProcessing = isProcessing;
        this.chatInput.disabled = isProcessing;
        
        // Update status badge
        const statusBadge = this.assistantStatus.querySelector('.badge');
        
        if (isProcessing) {
            statusBadge.textContent = 'Processing';
            statusBadge.className = 'badge bg-warning';
        } else {
            statusBadge.textContent = 'Idle';
            statusBadge.className = 'badge bg-secondary';
        }
    }
    
    formatMarkdown(text) {
        // Very simple markdown formatting
        // Bold
        text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        
        // Italic
        text = text.replace(/\*(.*?)\*/g, '<em>$1</em>');
        
        // Code blocks with language
        text = text.replace(/```(\w+)?\n([\s\S]*?)```/g, (match, lang, code) => {
            return `<pre><code>${this.escapeHTML(code.trim())}</code></pre>`;
        });
        
        // Inline code
        text = text.replace(/`(.*?)`/g, '<code>$1</code>');
        
        // Lists
        text = text.replace(/^\s*[\-\*]\s+(.*?)$/gm, '<li>$1</li>');
        text = text.replace(/(<li>.*?<\/li>)(?!\s*<li>)/gs, '<ul>$1</ul>');
        
        // Numbered lists
        text = text.replace(/^\s*(\d+)\.\s+(.*?)$/gm, '<li>$2</li>');
        text = text.replace(/(<li>.*?<\/li>)(?!\s*<li>)/gs, '<ol>$1</ol>');
        
        // Paragraphs
        text = text.replace(/(?:\r\n|\r|\n){2,}/g, '</p><p>');
        text = `<p>${text}</p>`;
        
        // Fix any nested paragraphs in lists
        text = text.replace(/<li><p>(.*?)<\/p><\/li>/g, '<li>$1</li>');
        
        return text;
    }
    
    escapeHTML(str) {
        return str
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }
    addReasoningSummary(summaryText) {
        if (summaryText && summaryText.length > 0) {
            const summaryEl = document.createElement('div');
            summaryEl.className = 'reasoning-summary';
            summaryEl.textContent = summaryText;
            this.chatMessages.appendChild(summaryEl);
        }
    }
    handleWebSearchCall(status) {
        // Create a message element for the web search status
        const webSearchMessage = document.createElement('div');
        webSearchMessage.className = 'web-search-message'; // Use a specific class for styling

        // Use an icon (e.g., magnifying glass or globe) and the status text
        webSearchMessage.innerHTML = `<i class="fas fa-search"></i> ${this.escapeHTML('Searching the web...')}`; // Example using Font Awesome icon

        this.chatMessages.appendChild(webSearchMessage);
        this.scrollToBottom();

        // Reset current assistant message if needed, similar to tool calls
        this.currentAssistantMessage = null;
    }
}

// Initialize on document ready
document.addEventListener('DOMContentLoaded', () => {
    console.log("Initializing chat assistant with global socket");
    // Use the global socket that's initialized in the HTML head
    const chatAssistant = new ChatAssistant(window.socket);
    window.chatAssistant = chatAssistant;
});