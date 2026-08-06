import React, { useState } from 'react';
import { Navbar } from '../components/Navbar';
import { Sidebar } from '../components/Sidebar';
import { ChatMessage } from '../components/ChatMessage';
import { streamChatQuery } from '../api/client';
import { Send, Loader2, Sparkles } from 'lucide-react';

export const ChatPage = () => {
    const [messages, setMessages] = useState([
        {
            role: 'assistant',
            content: 'Hello! Upload your company documents on the left panel, and ask me any question. I will provide accurate answers with inline citations.',
            sources: []
        }
    ]);
    const [inputQuery, setInputQuery] = useState('');
    const [loading, setLoading] = useState(false);
    const [refreshTrigger, setRefreshTrigger] = useState(0);

    const handleSend = async (e) => {
        e.preventDefault();
        if (!inputQuery.trim() || loading) return;

        const userQuery = inputQuery.trim();
        setInputQuery('');
        setLoading(true);

        // Add user prompt and create blank assistant placeholder for live stream
        setMessages((prev) => [
            ...prev,
            { role: 'user', content: userQuery, sources: [] },
            { role: 'assistant', content: '', sources: [] }
        ]);

        try {
            await streamChatQuery(
                userQuery,
                (sources) => {
                    // Update sources on placeholder message
                    setMessages((prev) => {
                        const updated = [...prev];
                        const lastIndex = updated.length - 1;
                        updated[lastIndex] = {
                            ...updated[lastIndex],
                            sources: sources
                        };
                        return updated;
                    });
                },
                (token) => {
                    // Append incoming stream tokens to the assistant message
                    setMessages((prev) => {
                        const updated = [...prev];
                        const lastIndex = updated.length - 1;
                        updated[lastIndex] = {
                            ...updated[lastIndex],
                            content: updated[lastIndex].content + token
                        };
                        return updated;
                    });
                }
            );
        } catch (err) {
            console.error('Streaming error:', err);
            setMessages((prev) => {
                const updated = [...prev];
                const lastIndex = updated.length - 1;
                if (!updated[lastIndex].content) {
                    updated[lastIndex] = {
                        role: 'assistant',
                        content: 'Sorry, an error occurred while searching your documents. Please try again.',
                        sources: []
                    };
                }
                return updated;
            });
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="app-container">
            <Navbar />
            <div className="main-layout">
                <Sidebar refreshTrigger={refreshTrigger} />

                <main className="chat-viewport">
                    <div className="messages-container">
                        {messages.map((msg, index) => (
                            <ChatMessage key={index} message={msg} />
                        ))}
                        {loading && messages[messages.length - 1]?.role === 'assistant' && !messages[messages.length - 1]?.content && (
                            <div className="chat-row assistant-row">
                                <div className="avatar"><Sparkles size={18} className="animate-pulse" /></div>
                                <div className="message-bubble loading-bubble">
                                    <Loader2 className="animate-spin" size={18} />
                                    <span>Searching vector database & synthesizing grounded answer...</span>
                                </div>
                            </div>
                        )}
                    </div>

                    <form className="chat-input-area" onSubmit={handleSend}>
                        <div className="input-glass-wrapper">
                            <input
                                type="text"
                                placeholder="Ask anything about your uploaded documents..."
                                value={inputQuery}
                                onChange={(e) => setInputQuery(e.target.value)}
                                disabled={loading}
                            />
                            <button type="submit" className="btn-send" disabled={loading || !inputQuery.trim()}>
                                <Send size={18} />
                            </button>
                        </div>
                    </form>
                </main>
            </div>
        </div>
    );
};