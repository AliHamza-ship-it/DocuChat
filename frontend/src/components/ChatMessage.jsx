import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
import { SourceCard } from './SourceCard';
import { Sparkles, User, Layers } from 'lucide-react';

export const ChatMessage = ({ message }) => {
    const isUser = message.role === 'user';

    const formattedContent = message.content
        ? message.content.replace(/<br\s*\/?>/gi, '<br />')
        : '';

    return (
        <div className={`chat-row ${isUser ? 'user-row' : 'assistant-row'}`}>
            <div className={`avatar ${isUser ? 'user-avatar' : 'assistant-avatar'}`}>
                {isUser ? <User size={18} /> : <Sparkles size={18} />}
            </div>
            <div className="message-bubble">
                <div className="message-text">
                    {isUser ? (
                        message.content
                    ) : (
                        <ReactMarkdown
                            remarkPlugins={[remarkGfm]}
                            rehypePlugins={[rehypeRaw]}
                            components={{
                                table: ({ node, ...props }) => <table className="markdown-table" {...props} />,
                                th: ({ node, ...props }) => <th className="markdown-th" {...props} />,
                                td: ({ node, ...props }) => <td className="markdown-td" {...props} />
                            }}
                        >
                            {formattedContent}
                        </ReactMarkdown>
                    )}
                </div>

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