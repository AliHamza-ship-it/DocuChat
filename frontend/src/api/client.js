import axios from 'axios';

const API_BASE_URL = 'http://localhost:8000/api';

const api = axios.create({
    baseURL: API_BASE_URL,
});

api.interceptors.request.use((config) => {
    const token = localStorage.getItem('docuchat_token');
    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

export const streamChatQuery = async (query, sessionId, onMeta, onSources, onToken) => {
    const token = localStorage.getItem('docuchat_token');

    const response = await fetch('http://localhost:8000/api/chat/query', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
            query: query,
            session_id: sessionId
        })
    });

    if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        buffer = lines.pop();

        for (const rawLine of lines) {
            const line = rawLine.trim();
            if (!line) continue;

            if (line.startsWith('data: ')) {
                const dataStr = line.slice(6).trim();
                if (dataStr === '[DONE]') return;

                try {
                    const parsed = JSON.parse(dataStr);

                    if (parsed.type === 'meta' && onMeta) {
                        onMeta(parsed);
                        if (parsed.sources && onSources) onSources(parsed.sources, parsed.session_id);
                    } else if (parsed.type === 'sources' && onSources) {
                        onSources(parsed.sources, parsed.session_id);
                    } else if (parsed.type === 'token' && onToken) {
                        // Pass the session_id to properly route the token
                        onToken(parsed.content, parsed.session_id);
                    }
                } catch (e) {
                    console.error('Error parsing SSE data:', e, dataStr);
                }
            }
        }
    }
};

export default api;