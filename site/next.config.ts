import type { NextConfig } from "next";

// A static export: the page is built once from the newest report and served as files.
const config: NextConfig = { output: "export" };

export default config;
