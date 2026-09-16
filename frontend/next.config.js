/** @type {import('next').NextConfig} */

// Stamped into the bundle at build time so the running app can say exactly
// which commit it was built from. Without this, "the deploy shows the old UI"
// is unfalsifiable - you cannot tell a stale bundle from a failed API call.
// Vercel sets VERCEL_GIT_COMMIT_SHA; locally we fall back to git.
function commitSha() {
  if (process.env.VERCEL_GIT_COMMIT_SHA) {
    return process.env.VERCEL_GIT_COMMIT_SHA.slice(0, 7);
  }
  try {
    return require("child_process")
      .execSync("git rev-parse --short HEAD", { stdio: ["ignore", "pipe", "ignore"] })
      .toString()
      .trim();
  } catch {
    return "unknown";
  }
}

const nextConfig = {
  reactStrictMode: true,
  env: {
    NEXT_PUBLIC_BUILD_SHA: commitSha(),
    NEXT_PUBLIC_BUILD_TIME: new Date().toISOString(),
  },
  async headers() {
    return [
      {
        // The dashboard is a client-rendered shell over live data. Letting a
        // CDN or browser hold the HTML means a new deploy can keep serving the
        // previous build's shell to an open tab, which looks exactly like the
        // update never shipped.
        source: "/:path*",
        headers: [
          { key: "Cache-Control", value: "public, max-age=0, must-revalidate" },
        ],
      },
    ];
  },
};

module.exports = nextConfig;
