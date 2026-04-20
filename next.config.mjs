/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  env: {
    OPENAI_API_KEY: process.env.OPENAI_API_KEY,
    PAPPERS_API_KEY: process.env.PAPPERS_API_KEY,
    SIRENE_API_TOKEN: process.env.SIRENE_API_TOKEN,
  },
};

export default nextConfig;
