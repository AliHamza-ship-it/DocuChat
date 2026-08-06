import React, { createContext, useContext, useState } from 'react';
import api from '../api/client';

const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
    const [user, setUser] = useState(() => {
        try {
            const storedUser = localStorage.getItem('docuchat_user');
            if (storedUser && storedUser !== "undefined" && storedUser !== "null") {
                return JSON.parse(storedUser);
            }
            return null;
        } catch {
            return null;
        }
    });

    const [token, setToken] = useState(() => {
        const storedToken = localStorage.getItem('docuchat_token');
        if (storedToken && storedToken !== "undefined" && storedToken !== "null") {
            return storedToken;
        }
        return null;
    });

    const [loading, setLoading] = useState(false);

    const login = async (email, password) => {
        setLoading(true);
        try {
            const res = await api.post('/auth/login', { email, password });

            const access_token = res.data.access_token || res.data.token;
            // Fallback: If backend returns a user object, use it; otherwise construct one from the logged in email
            const userData = res.data.user || { email: res.data.email || email };

            localStorage.setItem('docuchat_token', access_token);
            localStorage.setItem('docuchat_user', JSON.stringify(userData));

            setToken(access_token);
            setUser(userData);
            return { success: true };
        } catch (err) {
            return {
                success: false,
                error: err.response?.data?.detail || 'Login failed. Verify credentials.'
            };
        } finally {
            setLoading(false);
        }
    };

    const register = async (userData) => {
        setLoading(true);
        try {
            const res = await api.post('/auth/register', userData);
            return { success: true, message: res.data.message };
        } catch (err) {
            return { success: false, error: err.response?.data?.detail || 'Registration failed.' };
        } finally {
            setLoading(false);
        }
    };

    const logout = () => {
        localStorage.removeItem('docuchat_token');
        localStorage.removeItem('docuchat_user');
        setToken(null);
        setUser(null);
    };

    return (
        <AuthContext.Provider value={{ user, token, loading, login, register, logout }}>
            {children}
        </AuthContext.Provider>
    );
};

export const useAuth = () => useContext(AuthContext);