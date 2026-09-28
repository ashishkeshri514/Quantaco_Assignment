import {
  Badge,
  Button,
  Card,
  Drawer,
  Group,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchDashboard,
  fetchVenue,
  money,
  setToken,
  type DashboardData,
  type VenueDetail,
} from "./api";
import { useTransactionStream } from "./useTransactionStream";
import { VenuePanel } from "./VenuePanel";

type Props = {
  username: string;
  onLogout: () => void;
};

export function Dashboard({ username, onLogout }: Props) {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<VenueDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);
  const selectedIdRef = useRef<number | null>(null);
  selectedIdRef.current = selectedId;

  const refresh = useCallback(async () => {
    try {
      const next = await fetchDashboard();
      setData(next);
      setLastRefresh(new Date());
      setError(null);
      const id = selectedIdRef.current;
      if (id != null) {
        setDetail(await fetchVenue(id));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const scheduleRefresh = useCallback(() => {
    window.clearTimeout((window as unknown as { __opsRefresh?: number }).__opsRefresh);
    (window as unknown as { __opsRefresh?: number }).__opsRefresh = window.setTimeout(() => {
      void refresh();
    }, 400);
  }, [refresh]);

  const { connected } = useTransactionStream(true, scheduleRefresh);

  async function openVenue(id: number) {
    setSelectedId(id);
    setDetailLoading(true);
    try {
      setDetail(await fetchVenue(id));
    } finally {
      setDetailLoading(false);
    }
  }

  function closeVenue() {
    setSelectedId(null);
    setDetail(null);
  }

  function logout() {
    setToken(null);
    onLogout();
  }

  const rows = data?.venues.map((v, idx) => (
    <Table.Tr
      key={v.venue_id}
      bg={selectedId === v.venue_id ? "teal.0" : undefined}
      style={{ cursor: "pointer" }}
      onClick={() => void openVenue(v.venue_id)}
    >
      <Table.Td>{idx + 1}</Table.Td>
      <Table.Td>
        <Text fw={600} size="sm">
          {v.name}
        </Text>
        <Text size="xs" c="dimmed">
          {v.code}
        </Text>
      </Table.Td>
      <Table.Td>{v.city}</Table.Td>
      <Table.Td>{money(v.sales_today)}</Table.Td>
      <Table.Td>
        {v.sale_count}
        {v.void_refund_count > 0 && (
          <Text span size="xs" c="dimmed">
            {" "}
            · {v.void_refund_count} V/R
          </Text>
        )}
      </Table.Td>
      <Table.Td>
        {v.alerts.length === 0 ? (
          <Badge color="teal" variant="light">
            OK
          </Badge>
        ) : (
          <Group gap={4}>
            {v.alerts.map((a) => (
              <Badge key={a.type} color={a.severity === "high" ? "red" : "orange"} variant="light">
                {a.type === "sales_drop" ? "Drop" : "Voids"}
              </Badge>
            ))}
          </Group>
        )}
      </Table.Td>
    </Table.Tr>
  ));

  return (
    <>
      <Stack maw={1200} mx="auto" p="md" gap="md">
        <Group justify="space-between" align="flex-start">
          <div>
            <Title order={2}>Group Ops</Title>
            <Text size="sm" c="dimmed">
              Live trade across the group
            </Text>
          </div>
          <Group gap="sm">
            <Badge
              color={connected ? "teal" : "orange"}
              variant="light"
              leftSection={
                <span
                  style={{
                    width: 6,
                    height: 6,
                    borderRadius: "50%",
                    background: "currentColor",
                    display: "inline-block",
                  }}
                />
              }
            >
              {connected ? "Live" : "Reconnecting…"}
            </Badge>
            <Text size="sm" c="dimmed">
              {username}
            </Text>
            <Button variant="default" size="xs" onClick={logout}>
              Log out
            </Button>
          </Group>
        </Group>

        {error && (
          <Card withBorder padding="sm" bg="red.0" c="red">
            {error}
          </Card>
        )}

        {data && (
          <>
            <SimpleGrid cols={{ base: 1, sm: 2, md: 4 }}>
              <Kpi label="Group sales today" value={money(data.total_sales)} />
              <Kpi label="Venues" value={String(data.venue_count)} />
              <Kpi
                label="Sales / voids+refunds"
                value={`${data.sale_count} / ${data.void_refund_count}`}
              />
              <Kpi
                label="Venues flagged"
                value={String(data.alert_count)}
                warn={data.alert_count > 0}
              />
            </SimpleGrid>

            <SimpleGrid cols={{ base: 1, md: 3 }} spacing="md">
              <Card withBorder shadow="sm" padding="md" radius="md" style={{ gridColumn: "span 2" }}>
                <Group justify="space-between" mb="sm">
                  <Title order={4}>Venues by sales</Title>
                  {lastRefresh && (
                    <Text size="xs" c="dimmed">
                      Updated {lastRefresh.toLocaleTimeString()}
                    </Text>
                  )}
                </Group>
                <Table.ScrollContainer minWidth={520}>
                  <Table highlightOnHover verticalSpacing="sm">
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th>#</Table.Th>
                        <Table.Th>Venue</Table.Th>
                        <Table.Th>City</Table.Th>
                        <Table.Th>Sales</Table.Th>
                        <Table.Th>Txns</Table.Th>
                        <Table.Th>Status</Table.Th>
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>{rows}</Table.Tbody>
                  </Table>
                </Table.ScrollContainer>
              </Card>

              <Card withBorder shadow="sm" padding="md" radius="md">
                <Title order={4} mb="sm">
                  Top items (group)
                </Title>
                <Stack gap="xs">
                  {data.top_items.map((item) => (
                    <Group key={item.item_id} justify="space-between">
                      <Text size="sm">{item.name}</Text>
                      <Text size="sm" c="dimmed">
                        ×{item.qty} · {money(item.revenue)}
                      </Text>
                    </Group>
                  ))}
                  {!data.top_items.length && (
                    <Text size="sm" c="dimmed">
                      No sales yet — run the simulator.
                    </Text>
                  )}
                </Stack>
              </Card>
            </SimpleGrid>
          </>
        )}

        {!data && !error && (
          <Text c="dimmed" p="xl">
            Loading dashboard…
          </Text>
        )}
      </Stack>

      <Drawer
        opened={selectedId != null}
        onClose={closeVenue}
        position="right"
        size="md"
        title={detail?.name ?? "Venue"}
        padding="md"
        withOverlay={false}
        lockScroll={false}
      >
        <VenuePanel
          detail={detail}
          loading={detailLoading}
          onClose={closeVenue}
          onAcked={() => void refresh()}
          embedded
        />
      </Drawer>
    </>
  );
}

function Kpi({ label, value, warn = false }: { label: string; value: string; warn?: boolean }) {
  return (
    <Card withBorder shadow="sm" padding="md" radius="md" bg={warn ? "orange.0" : undefined}>
      <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
        {label}
      </Text>
      <Text mt={4} size="xl" fw={650} ff="Fraunces, Georgia, serif">
        {value}
      </Text>
    </Card>
  );
}
