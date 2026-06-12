import "./globals.css";

export const metadata = {
  title: "STICKBLADE ARENA — LLM Sword Duels",
  description:
    "Two LLM swordsmen. You choose which part of the blade is sharp. " +
    "Physics decides. Vote blind, build the leaderboard.",
  openGraph: {
    title: "STICKBLADE ARENA",
    description: "Watch LLMs sword-fight with real physics. Vote blind.",
  },
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <header className="site-head">
          <a href="/" className="logo">
            STICK<span className="blade">BLADE</span> ARENA
          </a>
          <nav>
            <a href="/">Fight</a>
            <a href="/leaderboard">Leaderboard</a>
            <a href="/history">History</a>
          </nav>
        </header>
        <main>{children}</main>
        <footer className="site-foot">
          physics-based LLM benchmark · vote blind · sharp zones change everything
        </footer>
      </body>
    </html>
  );
}
