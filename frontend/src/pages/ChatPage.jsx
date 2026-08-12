import React, { useState, useEffect, useRef } from 'react';
import { Navbar } from '../components/Navbar';
import { Sidebar } from '../components/Sidebar';
import { ChatMessage } from '../components/ChatMessage';
import { streamChatQuery } from '../api/client';
import api from '../api/client';
import { Send, Loader2, Sparkles } from 'lucide-react';

export const ChatPage = () => {
    // ... [Keep ALL your existing state, functions, and hooks exactly as they are] ...
    const [messages, setMessages] = useState([
        {
            role: 'assistant',
            content: 'Hello! Upload your company documents on the left panel, and ask me any question. I will provide accurate answers with inline citations.',
            sources: []
        }
    ]);
    const [inputQuery, setInputQuery] = useState('');
    const [generatingSessions, setGeneratingSessions] = useState(new Set());
    const [refreshTrigger, setRefreshTrigger] = useState(0);
    const [sessions, setSessions] = useState([]);
    const [activeSessionId, setActiveSessionId] = useState(`new_${Date.now()}`);

    const activeSessionRef = useRef(activeSessionId);
    const messagesEndRef = useRef(null);
    const scrollContainerRef = useRef(null);
    const isScrolledToBottom = useRef(true);

    useEffect(() => { activeSessionRef.current = activeSessionId; }, [activeSessionId]);

    const fetchSessions = async () => {
        try { const res = await api.get('/history/sessions'); setSessions(res.data); }
        catch (err) { console.error('Failed to load sessions', err); }
    };

    useEffect(() => { fetchSessions(); }, []);

    const handleScroll = () => {
        if (!scrollContainerRef.current) return;
        const { scrollTop, scrollHeight, clientHeight } = scrollContainerRef.current;
        isScrolledToBottom.current = Math.abs(scrollHeight - clientHeight - scrollTop) < 150;
    };

    useEffect(() => {
        if (isScrolledToBottom.current) {
            messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
        }
    }, [messages]);

    const handleSelectSession = async (sessionId) => {
        setActiveSessionId(sessionId);
        try {
            const res = await api.get(`/history/sessions/${sessionId}/messages`);
            if (res.data && res.data.length > 0) {
                setMessages(res.data);
                isScrolledToBottom.current = true;
                setTimeout(() => messagesEndRef.current?.scrollIntoView({ behavior: 'auto' }), 50);
            }
        } catch (err) { console.error('Failed to load messages', err); }
    };

    const handleNewChat = () => {
        setActiveSessionId(`new_${Date.now()}`);
        setMessages([{
            role: 'assistant',
            content: 'Hello! Upload your company documents on the left panel, and ask me any question. I will provide accurate answers with inline citations.',
            sources: []
        }]);
        isScrolledToBottom.current = true;
    };

    const handleDeleteSession = async (sessionId) => {
        try {
            await api.delete(`/history/sessions/${sessionId}`);
            if (activeSessionId === sessionId) handleNewChat();
            fetchSessions();
        } catch (err) { console.error('Failed to delete session', err); }
    };

    const isCurrentLoading = generatingSessions.has(activeSessionId);

    const handleSend = async (e) => {
        e.preventDefault();
        if (!inputQuery.trim() || isCurrentLoading) return;

        const userQuery = inputQuery.trim();
        setInputQuery('');
        isScrolledToBottom.current = true;
        setTimeout(() => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 50);

        const targetViewId = activeSessionId;
        let currentSessionId = targetViewId;
        setGeneratingSessions(prev => new Set(prev).add(targetViewId));

        setMessages((prev) => [
            ...prev,
            { role: 'user', content: userQuery, sources: [] },
            { role: 'assistant', content: '', sources: [] }
        ]);

        const backendSessionId = String(targetViewId).startsWith('new_') ? null : targetViewId;

        try {
            await streamChatQuery(
                userQuery,
                backendSessionId,
                (meta) => {
                    if (meta.is_new_session) {
                        const newDbId = meta.session_id;
                        setGeneratingSessions(prev => {
                            const next = new Set(prev);
                            next.delete(currentSessionId);
                            next.add(newDbId);
                            return next;
                        });
                        currentSessionId = newDbId;
                        if (activeSessionRef.current === targetViewId) setActiveSessionId(newDbId);
                        fetchSessions();
                    }
                },
                (sources, streamSessionId) => {
                    if (activeSessionRef.current === streamSessionId || activeSessionRef.current === targetViewId || activeSessionRef.current === currentSessionId) {
                        setMessages((prev) => {
                            if (prev.length === 0) return prev;
                            const lastIdx = prev.length - 1;
                            const lastMsg = prev[lastIdx];
                            return [...prev.slice(0, lastIdx), { ...lastMsg, sources: sources }];
                        });
                    }
                },
                (token, streamSessionId) => {
                    if (activeSessionRef.current === streamSessionId || activeSessionRef.current === targetViewId || activeSessionRef.current === currentSessionId) {
                        setMessages((prev) => {
                            if (prev.length === 0) return prev;
                            const lastIdx = prev.length - 1;
                            const lastMsg = prev[lastIdx];
                            return [...prev.slice(0, lastIdx), { ...lastMsg, content: lastMsg.content + token }];
                        });
                    }
                }
            );
        } catch (err) {
            console.error('Streaming error:', err);
            if (activeSessionRef.current === targetViewId || activeSessionRef.current === currentSessionId) {
                setMessages((prev) => {
                    if (prev.length === 0) return prev;
                    const lastIdx = prev.length - 1;
                    const lastMsg = prev[lastIdx];
                    if (!lastMsg.content) {
                        return [...prev.slice(0, lastIdx), {
                            role: 'assistant',
                            content: 'Sorry, an error occurred while searching your documents. Please try again.',
                            sources: []
                        }];
                    }
                    return prev;
                });
            }
        } finally {
            setGeneratingSessions(prev => {
                const next = new Set(prev);
                next.delete(targetViewId);
                next.delete(currentSessionId);
                return next;
            });
        }
    };

    return (
        <div className="app-container">
            <Navbar />
            <div className="main-layout">
                <Sidebar
                    refreshTrigger={refreshTrigger}
                    sessions={sessions}
                    activeSessionId={activeSessionId}
                    onSelectSession={handleSelectSession}
                    onNewChat={handleNewChat}
                    onDeleteSession={handleDeleteSession}
                />

                <main className="chat-viewport">
                    {/* The structural fix: Removed the "chat-content-container" wrapper so flexbox works! */}
                    <div
                        className="messages-container"
                        ref={scrollContainerRef}
                        onScroll={handleScroll}
                    >
                        {messages.map((msg, index) => (
                            <ChatMessage key={msg.id || index} message={msg} />
                        ))}

                        {isCurrentLoading && messages[messages.length - 1]?.role === 'assistant' && !messages[messages.length - 1]?.content && (
                            <div className="chat-row assistant-row">
                                <div className="avatar assistant-avatar">
                                    <Sparkles size={18} className="animate-pulse" />
                                </div>
                                <div className="message-bubble loading-bubble">
                                    <Loader2 className="animate-spin" size={18} />
                                    <span>Synthesizing answer from your knowledge base...</span>
                                </div>
                            </div>
                        )}
                        <div ref={messagesEndRef} />
                    </div>

                    {/* Because the wrapper is gone, this is now pushed perfectly to the bottom */}
                    <form className="chat-input-area" onSubmit={handleSend}>
                        <div className="input-glass-wrapper">
                            <input
                                type="text"
                                placeholder="Ask anything about your uploaded documents..."
                                value={inputQuery}
                                onChange={(e) => setInputQuery(e.target.value)}
                                disabled={isCurrentLoading}
                            />
                            <button type="submit" className="btn-send" disabled={isCurrentLoading || !inputQuery.trim()}>
                                <Send size={18} />
                            </button>
                        </div>
                    </form>
                </main>
            </div>
        </div>
    );
};