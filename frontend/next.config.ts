import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Allow the standalone output for Docker/Railway deployments
  output: "standalone",
};

export default nextConfig;
