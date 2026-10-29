import type { Metadata } from "next";
import "@/styles/ie.css";

// Kept out of search engines until the source lists' republication terms are
// settled (PARKING.md, licence): the page is built and served locally only.
export const metadata: Metadata = {
  title: "Ireland's grid connection queue",
  description: "Weekly report on projects waiting to connect to Ireland's electricity grid.",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-GB">
      <body>
        <a className="skip" href="#content">
          Skip to content
        </a>
        <main id="content" tabIndex={-1}>
          {children}
        </main>
        <footer className="muted">
          <p>
            Sources: EirGrid contracted generator lists (Supported by EirGrid Group Data); ESB
            Networks DSO contracted and energised lists, © ESB Networks; county lookups ©
            OpenStreetMap contributors, available under the{" "}
            <a href="https://www.openstreetmap.org/copyright">Open Database License</a>.
          </p>
          <p>ESB Networks and EirGrid have each given permission to use their lists here. Not endorsed by either.</p>
        </footer>
      </body>
    </html>
  );
}
