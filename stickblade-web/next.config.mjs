/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  env: {
    // Point this at your deployed FastAPI backend (HF Space URL).
    NEXT_PUBLIC_API_BASE:
      process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000",
  },
};
export default nextConfig;
