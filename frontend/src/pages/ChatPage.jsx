import React, { useState } from 'react';
import { Navbar } from '../components/Navbar';
import { Sidebar } from '../components/Sidebar';
import { ChatMessage } from '../components/ChatMessage';
import api from '../api/client';
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

        const userMessage = { role: 'user', content: inputQuery, sources: [] };
        setMessages((prev) => [...prev, userMessage]);
        const currentQuery = inputQuery;
        setInputQuery('');
        setLoading(true);

        try {
            const res = await api.post('/chat/query', { query: currentQuery });
            const assistantMessage = {
                role: 'assistant',
                content: res.data.answer,
                sources: res.data.sources
            };
            setMessages((prev) => [...prev, assistantMessage]);
        } catch (err) {
            setMessages((prev) => [
                ...prev,
                {
                    role: 'assistant',
                    content: 'Sorry, an error occurred while searching your documents. Please try again.',
                    sources: []
                }
            ]);
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
                        {loading && (
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