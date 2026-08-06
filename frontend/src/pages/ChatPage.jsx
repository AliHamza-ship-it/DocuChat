import React, { useState, useEffect, useRef } from 'react';
import { Navbar } from '../components/Navbar';
import { Sidebar } from '../components/Sidebar';
import { ChatMessage } from '../components/ChatMessage';
import { streamChatQuery } from '../api/client';
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

    // Tracks locked generating sessions
    const [generatingSessions, setGeneratingSessions] = useState(new Set());
    const [refreshTrigger, setRefreshTrigger] = useState(0);

    const [sessions, setSessions] = useState([]);

    // Default initial new chat gets a unique temp ID so streams don't bleed
    const [activeSessionId, setActiveSessionId] = useState(`new_${Date.now()}`);

    // Refs for safe cross-chat generation and smart scrolling
    const activeSessionRef = useRef(activeSessionId);
    const messagesEndRef = useRef(null);
    const scrollContainerRef = useRef(null);
    const isScrolledToBottom = useRef(true);

    useEffect(() => {
        activeSessionRef.current = activeSessionId;
    }, [activeSessionId]);

    const fetchSessions = async () => {
        try {
            const res = await api.get('/history/sessions');
            setSessions(res.data);
        } catch (err) {
            console.error('Failed to load sessions', err);
        }
    };

    useEffect(() => {
        fetchSessions();
    }, []);

    // Smart Scroll: Check if user is at the bottom (Increased threshold to 150px)
    const handleScroll = () => {
        if (!scrollContainerRef.current) return;
        const { scrollTop, scrollHeight, clientHeight } = scrollContainerRef.current;
        isScrolledToBottom.current = Math.abs(scrollHeight - clientHeight - scrollTop) < 150;
    };

    useEffect(() => {
        if (isScrolledToBottom.current) {
            messagesEndRef.current?.scrollIntoView({ behavior: 'auto' });
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
        } catch (err) {
            console.error('Failed to load messages', err);
        }
    };

    const handleNewChat = () => {
        // Assign a distinct ID to every new chat attempt
        setActiveSessionId(`new_${Date.now()}`);
        setMessages([
            {
                role: 'assistant',
                content: 'Hello! Upload your company documents on the left panel, and ask me any question. I will provide accurate answers with inline citations.',
                sources: []
            }
        ]);
        isScrolledToBottom.current = true;
    };

    const handleDeleteSession = async (sessionId) => {
        try {
            await api.delete(`/history/sessions/${sessionId}`);
            if (activeSessionId === sessionId) {
                handleNewChat();
            }
            fetchSessions();
        } catch (err) {
            console.error('Failed to delete session', err);
        }
    };

    const isCurrentLoading = generatingSessions.has(activeSessionId);

    const handleSend = async (e) => {
        e.preventDefault();
        if (!inputQuery.trim() || isCurrentLoading) return;

        const userQuery = inputQuery.trim();
        setInputQuery('');

        isScrolledToBottom.current = true;
        setTimeout(() => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 50);

        // Lock generation for THIS specific frontend view
        const targetViewId = activeSessionId;
        setGeneratingSessions(prev => new Set(prev).add(targetViewId));

        setMessages((prev) => [
            ...prev,
            { role: 'user', content: userQuery, sources: [] },
            { role: 'assistant', content: '', sources: [] }
        ]);

        // If it starts with 'new_', it's not a real DB session yet, pass null to backend
        const backendSessionId = String(targetViewId).startsWith('new_') ? null : targetViewId;

        try {
            await streamChatQuery(
                userQuery,
                backendSessionId,
                (meta) => {
                    if (meta.is_new_session) {
                        const newDbId = meta.session_id;

                        // Transfer the generation lock to the real database ID
                        setGeneratingSessions(prev => {
                            const next = new Set(prev);
                            next.delete(targetViewId);
                            next.add(newDbId);
                            return next;
                        });

                        // ONLY update the active view if the user hasn't clicked away
                        if (activeSessionRef.current === targetViewId) {
                            setActiveSessionId(newDbId);
                        }
                        fetchSessions();
                    }
                },
                (sources, streamSessionId) => {
                    // Strict Check: Only render if user is on the chat this token belongs to
                    if (activeSessionRef.current === streamSessionId || activeSessionRef.current === targetViewId) {
                        setMessages((prev) => {
                            if (prev.length === 0) return prev;
                            const lastIdx = prev.length - 1;
                            const lastMsg = prev[lastIdx];
                            return [
                                ...prev.slice(0, lastIdx),
                                { ...lastMsg, sources: sources }
                            ];
                        });
                    }
                },
                (token, streamSessionId) => {
                    // Strict Check: Only render if user is on the chat this token belongs to
                    if (activeSessionRef.current === streamSessionId || activeSessionRef.current === targetViewId) {
                        setMessages((prev) => {
                            if (prev.length === 0) return prev;
                            const lastIdx = prev.length - 1;
                            const lastMsg = prev[lastIdx];
                            return [
                                ...prev.slice(0, lastIdx),
                                { ...lastMsg, content: lastMsg.content + token }
                            ];
                        });
                    }
                }
            );
        } catch (err) {
            console.error('Streaming error:', err);
            // Show error message only if the user is still looking at the failed chat
            if (activeSessionRef.current === targetViewId || (backendSessionId && activeSessionRef.current === backendSessionId)) {
                setMessages((prev) => {
                    if (prev.length === 0) return prev;
                    const lastIdx = prev.length - 1;
                    const lastMsg = prev[lastIdx];
                    if (!lastMsg.content) {
                        return [
                            ...prev.slice(0, lastIdx),
                            {
                                role: 'assistant',
                                content: 'Sorry, an error occurred while searching your documents. Please try again.',
                                sources: []
                            }
                        ];
                    }
                    return prev;
                });
            }
        } finally {
            // Unlock generation
            setGeneratingSessions(prev => {
                const next = new Set(prev);
                next.delete(targetViewId);
                // Also clean up by checking all session states
                for (const item of next) {
                    if (String(item).startsWith('new_') && item !== activeSessionRef.current) {
                        next.delete(item);
                    }
                }
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
                                <div className="avatar"><Sparkles size={18} className="animate-pulse" /></div>
                                <div className="message-bubble loading-bubble">
                                    <Loader2 className="animate-spin" size={18} />
                                    <span>Searching vector database & synthesizing grounded answer...</span>
                                </div>
                            </div>
                        )}
                        <div ref={messagesEndRef} />
                    </div>

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