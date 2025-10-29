'use client';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { createClient } from '@/lib/supabase/client';

export default function SignUpPage() {
  const supabase = createClient();
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [buid, setbuid] = useState('');
  const [studentName, setStudentName] = useState('');
  const handleSignUp = async (e: React.FormEvent) => {
  e.preventDefault();
  setError("");

  // 👇 Example: insert into your custom table
  const { error } = await supabase
    .from('User_Information') // <-- replace with your actual table name
    .insert([
      {
        username: email,      // or another variable you collected
        buid: buid,           // add from a form field if you have one
        password: password,   // ⚠️ don't store plaintext passwords in production!
        Student_Name: studentName, // add a state variable for this
      },
    ]);

  if (error) {
    console.error(error);
    setError(error.message);
  } else {
    router.push('/chat'); // redirect after successful insert
  }
};

  return (
    <div className="flex items-center justify-center min-h-screen bg-gradient-to-r from-indigo-500 to-purple-600">
      <form
        onSubmit={handleSignUp}
        className="bg-white p-8 rounded-2xl shadow-md flex flex-col w-80 space-y-4"
      >
        <h1 className="text-xl font-semibold text-center">Create Account</h1>
        <input
          type="text"
          placeholder="John Doe"
          className="border rounded p-2"
          value={studentName}
          onChange={(e) => setStudentName(e.target.value)}
        />
        <input
          type="text"
          placeholder="U67676767"
          className="border rounded p-2"
          value={buid}
          onChange={(e) => setbuid(e.target.value)}
        />
        <input
          type="email"
          placeholder="Email"
          className="border rounded p-2"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        
        <input
          type="password"
          placeholder="Password"
          className="border rounded p-2"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        {error && <p className="text-red-500 text-sm">{error}</p>}
        <button
          type="submit"
          className="bg-indigo-600 text-white py-2 rounded hover:bg-indigo-700"
        >
          Sign Up
        </button>
      </form>
    </div>
  );
}
