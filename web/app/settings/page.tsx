"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Bell, MagnifyingGlass, ShieldWarning, TelegramLogo, Warning } from "@phosphor-icons/react";
import { api, AgentStatus, RosterInfo, StrategyProfile } from "@/lib/api";

const services = ["Agent", "Exchange API", "Dashboard", "Database", "Nginx"];

function Row({ icon, title, subtitle, children }: { icon: React.ReactNode; title: string; subtitle: string; children: React.ReactNode }) {
  return (
    <section className="flex min-h-[92px] items-center gap-5 border-b border-[#20303a] px-7 py-5">
      <div className="grid w-9 place-items-center text-[#dce5ed]">{icon}</div>
      <div className="w-[280px]">
        <h2 className="text-[14px] font-semibold text-[#e3eaf0]">{title}</h2>
        <p className="mt-1 text-[11px] text-[#82929d]">{subtitle}</p>
      </div>
      <div className="flex flex-1 items-center justify-between gap-8">{children}</div>
    </section>
  );
}

export default function SettingsPage() {
  const [halted, setHalted] = useState(false);
  const [haltPending, setHaltPending] = useState(false);
  const [agent, setAgent] = useState<AgentStatus | null>(null);
  const [statusError, setStatusError] = useState(false);
  const [roster, setRoster] = useState<RosterInfo | null>(null);
  const [profile, setProfile] = useState<StrategyProfile | null>(null);

  useEffect(() => {
    let active = true;
    const load = () => {
      api.agentStatus().then((next) => { if (active) { setAgent(next); setStatusError(false); setHalted(Boolean(next.kill_switch_active)); } }).catch(() => active && setStatusError(true));
      api.roster().then((next) => active && setRoster(next)).catch(() => {});
      api.strategyProfile().then((next) => active && setProfile(next)).catch(() => {});
    };
    load();
    const timer = window.setInterval(load, 10000);
    return () => { active = false; window.clearInterval(timer); };
  }, []);

  const onHalt = () => {
    setHaltPending(true);
    api.setKillSwitch(!halted, !halted ? "Manual halt from settings" : "Manual resume from settings")
      .then((res) => setHalted(res.kill_switch_active))
      .catch(() => setStatusError(true))
      .finally(() => setHaltPending(false));
  };

  const anyServiceError = agent ? Object.values(agent).some((value) => value === "error") : false;

  return (
    <div className="min-h-screen min-w-[1186px] bg-[#04090e] text-[#dce5ed]">
      <main className="flex min-h-screen flex-col">
        <header className="flex h-[70px] items-center justify-between border-b border-[#1a2b35] px-8">
          <h1 className="text-[22px] font-semibold">Settings</h1>
          <div className="flex items-center gap-7 text-[11px]">
            <span>Environment <b className="ml-2 rounded bg-[#164d2d] px-2 py-1 text-[#6ee392]">{agent?.testnet === false ? "LIVE" : "TESTNET"}</b></span>
            <span>Health <b className={statusError ? "ml-2 text-[#e4b63e]" : "ml-2 text-[#6ee392]"}>● {statusError ? "API UNAVAILABLE" : "ALL SYSTEMS OPERATIONAL"}</b></span>
            <Bell size={18} />
          </div>
        </header>
        <div className="min-w-0 flex-1 px-7">
          <Row icon={<ShieldWarning size={29} />} title="Trading Mode" subtitle="Environment for order execution — set via server config, not switchable here.">
            <div className="flex h-11 w-[310px] items-center border border-[#67d649] px-4 text-[13px] font-semibold text-[#70e94e]">
              {agent?.testnet === false ? "LIVE" : "TESTNET"}
            </div>
            <p className="w-[370px] text-[12px] text-[#9aa8b2]">Switching modes requires a config change and restart on the server — not exposed here to avoid an accidental live-mode flip.</p>
          </Row>
          <Row icon={<span className="text-[30px] text-[#f0b52d]">◆</span>} title="Exchange Connection" subtitle="Live status of the exchange connection.">
            <div className="flex flex-1 items-center gap-8 text-[12px]">
              <div>
                <span className="block text-[#83939f]">Exchange</span>
                <b>{agent?.exchange === "ok" ? "Connected" : "Checking"} <small className={`rounded px-2 py-1 ${agent?.exchange === "ok" ? "bg-[#164429] text-[#59dc81]" : "bg-[#3a2a12] text-[#e2b33d]"}`}>{agent?.exchange === "ok" ? "OK" : "CHECKING"}</small></b>
              </div>
              <div>
                <span className="block text-[#83939f]">Symbols tracked</span>
                <b>{agent?.symbols?.length ?? "—"}</b>
              </div>
            </div>
          </Row>
          <Row icon={<TelegramLogo size={30} weight="fill" color="#4ca9f0" />} title="Telegram Notifications" subtitle="Alerts are configured via the server .env — not yet editable from this dashboard.">
            <p className="flex-1 text-[12px] text-[#9aa8b2]">Trade open/close, CHoCH structure alerts, and daily summaries are sent per the bot&apos;s current config. To change what&apos;s sent, update the VPS <code>.env</code> directly.</p>
          </Row>
          <Row icon={<span className="grid h-7 w-7 place-items-center rounded-full border-2 border-[#dce5ed] text-[13px]">⊙</span>} title="Strategy Profile" subtitle="Active decision profile — see the Strategy page for full detail.">
            <div className="flex flex-1 items-center gap-6 text-[12px]">
              <div>
                <span className="block text-[#83939f]">Active profile</span>
                <b className="text-[14px] text-[#43aaff]">{profile?.profile ?? "—"}</b>
              </div>
              <div>
                <span className="block text-[#83939f]">Decision-active modules</span>
                <b>{profile?.decision_active?.length ?? "—"}</b>
              </div>
              <div>
                <span className="block text-[#83939f]">Observe-only modules</span>
                <b>{profile?.observe_only?.length ?? "—"}</b>
              </div>
            </div>
            <Link href="/strategy" className="text-[12px] text-[#c0ccd3]">View on Strategy page ›</Link>
          </Row>
          <Row icon={<MagnifyingGlass size={29} />} title="Scanner Settings" subtitle="Live roster scan status.">
            <div className="flex gap-10 text-[12px]">
              <div>
                <span className="block text-[#83939f]">Scan status</span>
                <b>{roster?.scan?.status ?? "—"}</b>
              </div>
              <div>
                <span className="block text-[#83939f]">Active roster size</span>
                <b>{roster?.active?.length ?? "—"}</b>
              </div>
              <div>
                <span className="block text-[#83939f]">Benched coins</span>
                <b>{roster?.benched?.length ?? "—"}</b>
              </div>
            </div>
          </Row>
          <Row icon={<span className="text-[25px]">⌁</span>} title="Services Health" subtitle="Real-time status of system services.">
            <div className="flex flex-1 justify-between">
              {services.map((service) => (
                <div key={service} className="text-center text-[11px]">
                  <b className={anyServiceError ? "text-[#ff646b]" : "text-[#55df82]"}>● {service}</b>
                  <span className="mt-1 block text-[#55df82]">{anyServiceError ? "Check" : "Healthy"}</span>
                </div>
              ))}
            </div>
            <Link href="/log" className="text-[12px] text-[#c0ccd3]">View Logs ↗</Link>
          </Row>
          <section className="flex min-h-[110px] items-center gap-5 border-t border-[#47272a] px-7 py-5">
            <Warning size={31} color="#ff555e" />
            <div className="w-[250px]">
              <h2 className="text-[14px] font-semibold text-[#ff686d]">Danger Zone</h2>
              <p className="mt-1 text-[11px] text-[#8796a0]">Critical actions. Proceed with caution.</p>
            </div>
            <div className="flex flex-1 items-start gap-3">
              <button onClick={onHalt} disabled={haltPending} className="border border-[#d93643] px-4 py-3 text-[11px] text-[#ff6168] disabled:opacity-50">
                Ⅱ {haltPending ? "Working…" : halted ? "Resume entries" : "Halt new entries"}
              </button>
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
