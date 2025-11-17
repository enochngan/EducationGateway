'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { createClient } from '@/lib/supabase/client';

export default function ChatPage() {
  const router = useRouter();
  const supabase = createClient();

  const [user, setUser] = useState<any>(null);
  const [messages, setMessages] = useState<{ role: string; content: string }[]>([]);
  const [input, setInput] = useState('');

  // Load persisted messages from localStorage
  useEffect(() => {
    try {
      const cached = localStorage.getItem('chat_messages');
      if (cached) setMessages(JSON.parse(cached));
    } catch (e) {
      console.warn('Failed to load cached messages', e);
    }
  }, []);

  // Persist messages whenever they change
  useEffect(() => {
    try {
      localStorage.setItem('chat_messages', JSON.stringify(messages));
    } catch (e) {
      console.warn('Failed to persist messages', e);
    }
  }, [messages]);

  // Fetch session on mount
  useEffect(() => {
    const storedUser = localStorage.getItem('user');
    console.log("bye")
    console.log(storedUser);
    if (!storedUser) {
      router.push('/auth/login'); // No one logged in → go back
    } else {
      console.log("hello");
      setUser(JSON.parse(storedUser));
    }   
  }, []);

  const handleSend = async () => {
    if (!input.trim()) return;

  const newMessages = [...messages, { role: 'user', content: input }];
  setMessages(newMessages);
  setInput('');


    const response = await fetch("http://localhost:8000/api/chat", {
    headers: {
    "Content-Type": "application/json",   // 👈 REQUIRED
  },
    method: "POST",
    body: JSON.stringify({input}),

    
});
  const data = await response.json();

  // Append the LLM reply to the current messages (use functional update to avoid stale state)
  setMessages((prev) => [...prev, { role: 'LLM', content: data.reply }]);
  };

  const handleLogout = async () => {
    localStorage.removeItem('user'); // ✅ clear stored user
    router.push('/auth/login');  
  };

  return (
    <div className="flex flex-col items-center min-h-screen bg-gray-900 text-white p-8">
      <div className="flex justify-between w-full max-w-3xl mb-6">
        <h1 className="text-2xl font-bold">LLM Chat Interface</h1>
        <button
          onClick={handleLogout}
          className="text-sm text-gray-300 hover:text-white underline"
        >
          Logout
        </button>
      </div>

      <div className="w-full max-w-3xl bg-gray-800 rounded-2xl p-4 flex flex-col space-y-3">
        <div className="flex-1 overflow-y-auto max-h-[60vh] space-y-2">
          {messages.map((m, i) => (
            <div
              key={i}
              className={`p-2 rounded-lg max-w-[75%] ${
                m.role === 'user'
                  ? 'bg-indigo-600 self-end ml-auto'
                  : 'bg-gray-700 self-start'
              }`}
            >
              {m.content}
            </div>
          ))}
        </div>

        <div className="flex space-x-2 mt-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask the AI..."
            className="flex-1 p-2 rounded bg-gray-700 text-white focus:outline-none"
          />
          <button
            onClick={handleSend}
            className="bg-indigo-600 px-4 py-2 rounded hover:bg-indigo-700"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
