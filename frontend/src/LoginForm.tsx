import {
  Alert,
  Button,
  Paper,
  PasswordInput,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useState, type FormEvent } from "react";
import { login, setToken } from "./api";

type Props = {
  onLoggedIn: (username: string) => void;
};

export function LoginForm({ onLoggedIn }: Props) {
  const [username, setUsername] = useState("ops");
  const [password, setPassword] = useState("ops1234");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await login(username, password);
      setToken(res.token);
      onLoggedIn(username);
    } catch {
      setError("Invalid credentials");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Stack mih="100vh" align="center" justify="center" p="xl">
      <Paper component="form" onSubmit={onSubmit} shadow="md" p="xl" radius="lg" w={400} maw="100%">
        <Stack gap="md">
          <Text c="teal" fw={650} ff="Fraunces, Georgia, serif">
            Group Ops
          </Text>
          <Title order={1} ff="Fraunces, Georgia, serif">
            Live trade desk
          </Title>
          <Text c="dimmed" size="sm">
            Watch sales across the hospitality group as they happen.
          </Text>

          <TextInput
            label="Username"
            value={username}
            onChange={(e) => setUsername(e.currentTarget.value)}
            autoComplete="username"
          />
          <PasswordInput
            label="Password"
            value={password}
            onChange={(e) => setPassword(e.currentTarget.value)}
            autoComplete="current-password"
          />

          {error && (
            <Alert color="red" variant="light">
              {error}
            </Alert>
          )}

          <Button type="submit" loading={loading} fullWidth>
            Sign in
          </Button>
          <Text size="xs" c="dimmed">
            Demo: ops / ops1234
          </Text>
        </Stack>
      </Paper>
    </Stack>
  );
}
