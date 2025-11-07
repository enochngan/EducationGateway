'use client';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { createClient } from '@/lib/supabase/client';

export default function LoginPage() {
  const router = useRouter();
  const supabase = createClient();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
  setError('');
  
  // 1. Query your custom user table
  const { data, error } = await supabase
    .from('user_information')
    .select('*')
    .eq('username', email)         // or whatever your login field is
    .eq('password', password);     // ⚠️ plain text passwords only for testing
  
  // 2. Handle any DB or logic errors
  if (error) {
    console.error(error);
    setError('Database error, please try again.');
    return;
  }

  // 3. If no match found
  if (!data || data.length === 0) {
    setError('Invalid username or password');
    return;
  }

  // 4. If user found, “log in”
  // Example: store user info in localStorage or context
  localStorage.setItem('user', JSON.stringify(data[0]));
  console.log(localStorage.getItem("user"));
  // 5. Redirect to chat
  router.push('/chat');
  };

  return (
    <div className="flex items-center justify-center min-h-screen bg-gradient-to-r from-indigo-500 to-purple-600">
      <form
        onSubmit={handleLogin}
        className="bg-white p-8 rounded-2xl shadow-md flex flex-col w-80 space-y-4"
      >
        <h1 className="text-xl font-semibold text-center text-gray-800">
          Welcome Back
        </h1>

        <input
          type="email"
          placeholder="Email"
          className="border rounded p-2 focus:outline-indigo-500"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <input
          type="password"
          placeholder="Password"
          className="border rounded p-2 focus:outline-indigo-500"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />

        {error && <p className="text-red-500 text-sm">{error}</p>}

        <button
          type="submit"
          className="bg-indigo-600 text-white py-2 rounded hover:bg-indigo-700"
        >
          Log In
        </button>

        <p className="text-sm text-center text-gray-600">
          Don’t have an account?{' '}
          <a href="/auth/sign-up" className="text-indigo-600 hover:underline">
            Sign Up
          </a>
        </p>
      </form>
    </div>
  );
}
