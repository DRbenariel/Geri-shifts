/** Static export: the mockup is plain HTML/JS, servable anywhere (Vercel preview, local file server). */
const nextConfig = {
  output: 'export',
  images: { unoptimized: true },
};
export default nextConfig;
