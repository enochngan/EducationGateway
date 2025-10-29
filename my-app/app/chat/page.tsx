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

  // Fetch session on mount
  useEffect(() => {
    // const storedUser = localStorage.getItem('user');
    // console.log("bye")
    // console.log(storedUser);
    // if (!storedUser) {
    //   router.push('/login'); // No one logged in → go back
    // } else {
    //   console.log("hello");
    //   setUser(JSON.parse(storedUser));
    // }
  }, []);

  const handleSend = async () => {
    if (!input.trim()) return;

    const newMessages = [...messages, { role: 'user', content: input }];
    setMessages(newMessages);
    setInput('');

    // Mock LLM response (replace with API route later)
    setTimeout(() => {
      setMessages([
        ...newMessages,
        { role: 'assistant', content: "🤖 This is an AI placeholder response." },
      ]);
    }, 600);
  };

  const handleLogout = async () => {
    // localStorage.removeItem('user'); // ✅ clear stored user
    // router.push('/login');  
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
