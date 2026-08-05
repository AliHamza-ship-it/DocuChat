import React from 'react';
import { SourceCard } from './SourceCard';
import { Bot, User, Layers } from 'lucide-react';

export const ChatMessage = ({ message }) => {
    const isUser = message.role === 'user';

    return (
        <div className={`chat-row ${isUser ? 'user-row' : 'assistant-row'}`}>
            <div className="avatar">
                {isUser ? <User size={18} /> : <Bot size={18} />}
            </div>
            <div className="message-bubble">
                <div className="message-text">{message.content}</div>

                {!isUser && message.sources && message.sources.length > 0 && (
                    <div className="citations-block">
                        <div className="citations-header">
                            <Layers size={14} />
                            <span>Grounded Context Sources ({message.sources.length})</span>
                        </div>
                        <div className="sources-grid">
                            {message.sources.map((src, i) => (
                                <SourceCard key={i} source={src} index={i} />
                            ))}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};