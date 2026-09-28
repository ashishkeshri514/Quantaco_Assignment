import "@mantine/core/styles.css";

import { MantineProvider } from "@mantine/core";
import { useState } from "react";
import { getToken } from "./api";
import { Dashboard } from "./Dashboard";
import { LoginForm } from "./LoginForm";
import { theme } from "./theme";

const pageBg =
  "radial-gradient(ellipse 70% 45% at 0% 0%, rgba(15,107,82,.12), transparent 55%), linear-gradient(165deg, #f4f7f2 0%, #eef2ec 45%, #e2e8df 100%)";

export default function App() {
  const [username, setUsername] = useState<string | null>(getToken() ? "ops" : null);

  return (
    <MantineProvider
      theme={theme}
      defaultColorScheme="light"
      cssVariablesResolver={() => ({
        variables: {},
        light: {
          "--mantine-color-body": "#eef2ec",
        },
        dark: {},
      })}
    >
      <div style={{ minHeight: "100vh", width: "100%", background: pageBg }}>
        {!username ? (
          <LoginForm onLoggedIn={setUsername} />
        ) : (
          <Dashboard username={username} onLogout={() => setUsername(null)} />
        )}
      </div>
    </MantineProvider>
  );
}
