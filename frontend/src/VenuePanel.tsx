import {
  Alert as MantineAlert,
  Badge,
  Button,
  Card,
  Group,
  Progress,
  SimpleGrid,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import { useState } from "react";
import { acknowledgeAlert, money, type Alert, type TopItem, type VenueDetail } from "./api";

type Props = {
  detail: VenueDetail | null;
  loading: boolean;
  onClose: () => void;
  onAcked?: () => void;
  /** When true, skip outer card/header (Drawer already provides them). */
  embedded?: boolean;
};

function AlertBadges({ alerts }: { alerts: Alert[] }) {
  if (!alerts.length) {
    return (
      <Badge color="teal" variant="light">
        OK
      </Badge>
    );
  }
  return (
    <Group gap={6}>
      {alerts.map((a) => (
        <Badge key={a.type + a.message} color={a.severity === "high" ? "red" : "orange"} variant="light">
          {a.type === "sales_drop" ? "Sales drop" : "Void/refund spike"}
        </Badge>
      ))}
    </Group>
  );
}

function ItemList({ items }: { items: TopItem[] }) {
  if (!items.length) {
    return (
      <Text c="dimmed" size="sm">
        No sales yet today.
      </Text>
    );
  }
  return (
    <Stack gap={6}>
      {items.map((item) => (
        <Group key={item.item_id} justify="space-between" gap="sm">
          <Text size="sm">{item.name}</Text>
          <Text size="sm" c="dimmed">
            ×{item.qty} · {money(item.revenue)}
          </Text>
        </Group>
      ))}
    </Stack>
  );
}

export function VenuePanel({ detail, loading, onAcked, embedded = false }: Props) {
  const [acking, setAcking] = useState<string | null>(null);

  async function mute(alertType: string) {
    if (!detail) return;
    setAcking(alertType);
    try {
      await acknowledgeAlert(detail.venue_id, alertType);
      onAcked?.();
    } finally {
      setAcking(null);
    }
  }

  const body = (
    <>
      {loading && !detail && (
        <Text c="dimmed" size="sm">
          Loading…
        </Text>
      )}

      {detail && (
        <Stack gap="md">
          {embedded && (
            <Text size="sm" c="dimmed">
              {detail.code} · {detail.city} · {detail.venue_type}
            </Text>
          )}

          <SimpleGrid cols={2}>
            <Card padding="sm" radius="sm" bg="teal.0">
              <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
                Sales today
              </Text>
              <Text fw={650} size="lg" ff="Fraunces, Georgia, serif">
                {money(detail.sales_today)}
              </Text>
            </Card>
            <Card padding="sm" radius="sm" bg="teal.0">
              <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
                Status
              </Text>
              <AlertBadges alerts={detail.alerts} />
            </Card>
          </SimpleGrid>

          {detail.alerts.map((a) => (
            <MantineAlert
              key={a.message}
              color={a.severity === "high" ? "red" : "orange"}
              variant="light"
              title={a.message}
            >
              <Button
                size="xs"
                variant="default"
                mt="xs"
                loading={acking === a.type}
                onClick={() => void mute(a.type)}
              >
                Mute today
              </Button>
            </MantineAlert>
          ))}

          <div>
            <Title order={5} mb="xs">
              Hourly trade
            </Title>
            {!detail.hourly_trade.length ? (
              <Text c="dimmed" size="sm">
                No hourly sales yet.
              </Text>
            ) : (
              <Stack gap="sm">
                {detail.hourly_trade.map((h) => {
                  const max = Math.max(
                    ...detail.hourly_trade.map((x) => Math.max(x.sales, x.baseline ?? 0)),
                    1
                  );
                  const label = new Date(h.hour).toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                  });
                  return (
                    <div key={h.hour}>
                      <Group justify="space-between" mb={4}>
                        <Text size="xs">{label}</Text>
                        <Text size="xs" c="dimmed">
                          {money(h.sales)}
                        </Text>
                      </Group>
                      <Progress value={(h.sales / max) * 100} color="teal" size="sm" radius="xl" />
                    </div>
                  );
                })}
              </Stack>
            )}
          </div>

          <div>
            <Title order={5} mb="xs">
              Top sellers
            </Title>
            <ItemList items={detail.top_items} />
          </div>
        </Stack>
      )}
    </>
  );

  if (embedded) return body;

  return (
    <Card shadow="sm" padding="lg" radius="md" withBorder>
      {body}
    </Card>
  );
}
