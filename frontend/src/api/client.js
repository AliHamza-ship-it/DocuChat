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

// Real-time stream reader function
export const streamChatQuery = async (query, onSources, onToken) => {
    const token = localStorage.getItem('docuchat_token');
    const response = await fetch(`${API_BASE_URL}/chat/query`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ query }),
    });

    if (!response.ok) {
        throw new Error(`HTTP error status: ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed.startsWith('data: ')) continue;
            const dataStr = trimmed.replace(/^data:\s*/, '');

            if (dataStr === '[DONE]') break;

            try {
                const parsed = JSON.parse(dataStr);
                if (parsed.type === 'sources' && onSources) {
                    onSources(parsed.sources);
                } else if (parsed.type === 'token' && onToken) {
                    onToken(parsed.content);
                }
            } catch (e) {
                console.error('Error parsing SSE line:', e);
            }
        }
    }
};

export default api;