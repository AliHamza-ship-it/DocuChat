import React from 'react';
import { BookOpen, FileCode } from 'lucide-react';

export const SourceCard = ({ source, index }) => {
    const filename = source.metadata?.source || 'Document';
    const page = source.metadata?.page ? `Page ${source.metadata.page}` : 'Chunk Context';
    const similarityScore = (source.similarity * 100).toFixed(1);

    return (
        <div className="source-card">
            <div className="source-card-header">
                <span className="source-badge">
                    <BookOpen size={13} /> Source #{index + 1}
                </span>
                <span className="similarity-badge">{similarityScore}% Match</span>
            </div>
            <div className="source-file-info">
                <FileCode size={14} />
                <span>{filename} ({page})</span>
            </div>
            <p className="source-content">"{source.content}"</p>
        </div>
    );
};