/* ============================================================================
   59b · KLIPPEYE SOFTWARE
   The page "Aggiornamenti" of the settings menu: which release is installed (backend, dashboard), whether a newer one
   is waiting, the button that installs it, the way back (rollback) and the restart of the backend.

   How an update gets here: the files of the new release are uploaded to the GitHub repository KlippEye lives in; Moonraker
   (its "update manager", configured by scripts/install.sh) compares the Raspberry's copy with that repository, and on
   "Aggiorna" downloads the difference and restarts the `klippeye` service. The settings, the AI key and the notification
   key live in another folder and are never touched. The update dialog itself is app/56-system.js.
   ========================================================================== */

// The names of the program's service and of its entry in Moonraker's update manager. An install that has not moved yet
// (still in ~/vzbot, see scripts/passa-a-klippeye.sh) has the old ones, "vzbot" and "vzbot-notifier": they are taken
// from what Moonraker reports (programEntry) and from the services it lists (notifierService), so both work.
let PROGRAM_COMPONENT = "klippeye";
let NOTIFIER_SERVICE = "klippeye-notifier";
const LEGACY_PROGRAM_COMPONENT = "vzbot";
const LEGACY_NOTIFIER_SERVICE = "vzbot-notifier";
const UPDATE_STATUS_POLL_MS = 30000;
const CHECK_SETTLE_MS = 700;
const RELEASE_TEXT = /^[0-9A-Za-z.+_-]{1,32}$/;
const REMOTE_RELEASE_TIMEOUT_MS = 6000;
const COMMITS_SHOWN = 6;
const INSTALL_COMMAND = "bash ~/klippeye/scripts/install.sh";

/** Moonraker's entry of the program in `versionInfo` (its own name, else the old one), and PROGRAM_COMPONENT follows; null when there is none. */
function programEntry(versionInfo) {
  const info = isPlainObject(versionInfo) ? versionInfo : {};
  const key = info[PROGRAM_COMPONENT] ? PROGRAM_COMPONENT : info["klippeye"] ? "klippeye" : info[LEGACY_PROGRAM_COMPONENT] ? LEGACY_PROGRAM_COMPONENT : PROGRAM_COMPONENT;
  PROGRAM_COMPONENT = key;
  NOTIFIER_SERVICE = key === LEGACY_PROGRAM_COMPONENT ? LEGACY_NOTIFIER_SERVICE : "klippeye-notifier";
  return info[key] && typeof info[key] === "object" ? info[key] : null;
}

/** The name of the notification service among the services Moonraker manages ("" when there is none). */
const notifierService = (services) => (Array.isArray(services) ? ["klippeye-notifier", LEGACY_NOTIFIER_SERVICE].find((name) => services.includes(name)) || "" : "");

/** "3 min", "2 h 10 min", "1 g 4 h": how long the backend has been running. */
function formatUptime(seconds) {
  const total = Math.max(0, Math.round(Number(seconds) || 0));
  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (days) return days + " g " + hours + " h";
  if (hours) return hours + " h " + minutes + " min";
  return Math.max(1, minutes) + " min";
}

const formatCommitDate = (unix) => {
  const seconds = Number(unix);
  return seconds > 0 ? new Date(seconds * 1000).toLocaleDateString(LOCALE, { day: "2-digit", month: "short" }) : "";
};

/** The address of the VERSION file of the repository Moonraker updates from, on raw.githubusercontent.com; "" when that is not GitHub. */
function remoteVersionUrl(info) {
  const url = String((info && (info.remote_url || info.recovery_url)) || "");
  const match = /github\.com[:/]([^/]+)\/([^/]+?)(?:\.git)?\/?$/.exec(url);
  if (!match) return "";
  // on the stable channel the update goes to the newest release tag (vX.Y.Z), not to the tip of the branch
  const tag = info && info.channel && info.channel !== "dev" && /^v\d+\.\d+\.\d+$/.test(String(info.remote_version || "")) ? String(info.remote_version) : "";
  const branch = tag || String((info && info.branch) || "main").replace(/[^A-Za-z0-9._/-]/g, "");
  return "https://raw.githubusercontent.com/" + match[1] + "/" + match[2] + "/" + branch + "/VERSION";
}

/**
 * The release written in the VERSION file of the repository (what the update would install), or null when it cannot be
 * known: not GitHub, no internet from this device, a private repository. A nicety: the update works without it.
 */
function useRemoteRelease(info) {
  const [release, setRelease] = useState(null);
  const url = remoteVersionUrl(info);
  const hash = (info && info.remote_hash) || "";
  useEffect(() => {
    setRelease(null);
    if (!url) return undefined;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), REMOTE_RELEASE_TIMEOUT_MS);
    fetch(url + "?t=" + Date.now(), { cache: "no-store", signal: controller.signal })
      .then((response) => (response.ok ? response.text() : ""))
      .then((text) => {
        const clean = String(text).trim();
        setRelease(RELEASE_TEXT.test(clean) ? clean : null);
      })
      .catch(noop)
      .finally(() => clearTimeout(timer));
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [url, hash]);
  return release;
}

/**
 * Moonraker's view of the KlippEye repository: { phase: "loading" | "ok" | "missing" (Moonraker does not know KlippEye)
 * | "down", raw (its status entry), busy, checking, check() (asks Moonraker to look at the repository now), reload() }.
 */
function useProgramUpdate(active) {
  const [state, setState] = useState({ phase: "loading", raw: null, busy: false });
  const [checking, setChecking] = useState(false);
  const [checkedAt, setCheckedAt] = useState(0);
  const readRef = useRef(noop);
  useEffect(() => {
    if (!active) return undefined;
    let cancelled = false;
    const read = async () => {
      const status = await fetchResult("/machine/update/status");
      if (cancelled) return;
      if (!status) return setState((previous) => (previous.phase === "ok" ? previous : { phase: "down", raw: null, busy: false }));
      const raw = programEntry(status.version_info);
      return setState(raw && typeof raw === "object" ? { phase: "ok", raw, busy: Boolean(status.busy) } : { phase: "missing", raw: null, busy: Boolean(status.busy) });
    };
    readRef.current = read;
    const stop = startPolling(read, UPDATE_STATUS_POLL_MS);
    return () => {
      cancelled = true;
      stop();
    };
  }, [active]);
  const check = async () => {
    setChecking(true);
    await refreshUpdateStatus();
    await sleep(CHECK_SETTLE_MS);
    await readRef.current();
    setCheckedAt(Date.now());
    setChecking(false);
  };
  return { ...state, checking, checkedAt, check, reload: () => readRef.current() };
}

/**
 * The update channel of KlippEye in Moonraker's update manager (/api/update/channel): { channel: "stable" | "dev" | null
 * (not listed) | undefined (not known yet), busy, set(channel) }. Changing it restarts Moonraker.
 */
const CHANNEL_SETTLE_MS = 6000;
function useUpdateChannel(active, onChanged) {
  const [state, setState] = useState({ channel: undefined, busy: false });
  const load = async () => {
    try {
      const answer = await fetchJson("/api/update/channel");
      setState({ channel: answer && answer.ok ? answer.channel : undefined, busy: false });
    } catch (e) {
      setState({ channel: undefined, busy: false });
    }
  };
  useEffect(() => {
    if (active) load();
  }, [active]);
  const set = async (channel) => {
    setState((previous) => ({ ...previous, busy: true }));
    try {
      const response = await fetchFresh("/api/update/channel", { method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ channel }), timeout: 30000 });
      const answer = await response.json().catch(() => ({}));
      if (!response.ok || !answer.ok) {
        toast.action(answer.error || tx("Error {status}", { status: response.status }));
        return load();
      }
      if (answer.changed) toast.notice(tx("Update channel changed: Moonraker restarts"), 3000);
      setState({ channel: answer.channel, busy: true });
      await sleep(CHANNEL_SETTLE_MS);
      setState({ channel: answer.channel, busy: false });
      onChanged();
    } catch (e) {
      toast.action(tx("Moonraker does not answer: try again shortly."));
      load();
    }
  };
  return { ...state, set };
}

function ChannelBlock({ channel, printing }) {
  if (channel.channel === undefined || channel.channel === null) return null;
  const options = [
    { id: "stable", label: tx("Stable releases"), detail: tx("Only the releases that passed all the tests (recommended)") },
    { id: "dev", label: tx("Every change"), detail: tx("Every change as soon as it is on GitHub: for testing new things") },
  ];
  const value = channel.channel === "dev" ? "dev" : "stable";
  return h(
    SettingsGroup,
    { title: tx("Update channel"), note: printing ? tx("A print is running: change it when the print ends (Moonraker restarts).") : tx("Moonraker restarts for a few seconds when the channel changes.") },
    h(ChoiceRows, { label: tx("Update channel"), options, value, onChange: (id) => !channel.busy && !printing && id !== value && channel.set(id) }),
  );
}

/* ---------------------------------------------------------------------------
   Pieces of the page
   ------------------------------------------------------------------------- */
const InfoLine = ({ label, value, warn }) => h("div", { className: "set-info" }, h("span", { className: "set-info__label" }, label), h("span", { className: cx("set-info__value", warn && "set-info__value--warn") }, value));

function CommitList({ commits }) {
  const list = Array.isArray(commits) ? commits.slice(0, COMMITS_SHOWN) : [];
  if (!list.length) return null;
  const more = commits.length - list.length;
  return h(
    "ul",
    { className: "set-commits" },
    list.map((commit, index) => h("li", { key: commit.sha || index }, h("span", { className: "set-commits__subject" }, commit.subject || tx("(no description)")), h("span", { className: "set-commits__date" }, formatCommitDate(commit.date)))),
    more > 0 && h("li", { className: "set-commits__more" }, tx("and {count} more changes", { count: more })),
  );
}

/** The state of Moonraker's side: what it says about the repository, and the buttons that follow from it. */
function UpdateBlock({ update, remoteRelease, brainRelease, printing, menu, updates }) {
  const { phase, raw } = update;
  if (phase === "loading") return h("div", { className: "set-status" }, h("span", { className: "set-status__dot" }), tx("Asking Moonraker whether there is something new…"));
  if (phase === "down") return h("div", { className: "set-status set-status--warn" }, h("span", { className: "set-status__dot" }), tx("Moonraker does not answer: cannot know whether there are updates."));
  if (phase === "missing") {
    return h(
      "div",
      { className: "set-status set-status--warn" },
      h("span", { className: "set-status__dot" }),
      h("span", null, tx("Moonraker does not know KlippEye among the programs it updates yet. On the Raspberry run "), h("code", null, INSTALL_COMMAND), tx(" (it links it) and then restart Moonraker from the Restart menu.")),
    );
  }
  const component = { ...describeComponent(PROGRAM_COMPONENT, raw), raw };
  const behind = raw.commits_behind_count != null ? Number(raw.commits_behind_count) : component.behind;
  const broken = raw.corrupt || raw.is_valid === false || raw.is_dirty;
  const open = (action) => {
    menu.close();
    action();
  };
  if (broken) {
    const why = (Array.isArray(raw.warnings) && raw.warnings.length ? raw.warnings.join(" ") : "") || (raw.is_dirty ? tx("Some program files on the Raspberry were changed by hand.") : tx("The program repository on the Raspberry is not in order."));
    return h(
      React.Fragment,
      null,
      h("div", { className: "set-status set-status--warn", role: "alert" }, h("span", { className: "set-status__dot" }), h("span", null, why + tx(" As long as it stays like this Moonraker refuses to update."))),
      h("button", { type: "button", className: "oui-btn oui-btn--block", onClick: () => open(() => updates.askRecover(component)) }, h(Icons.RotateCw, { size: 18 }), tx("Restore the program files")),
      h("p", { className: "set-group__note" }, tx("Brings the files back to the official release. Settings, AI key and notifications live in another folder and are not touched.")),
    );
  }
  if (behind > 0) {
    return h(
      React.Fragment,
      null,
      h(
        "div",
        { className: "set-status set-status--update" },
        h("span", { className: "set-status__dot" }),
        h("span", null, remoteRelease ? (brainRelease ? tx("Release {release} is available (you have {current})", { release: remoteRelease, current: brainRelease }) : tx("Release {release} is available", { release: remoteRelease })) : behind === 1 ? tx("Update available: 1 change coming") : tx("Update available: {count} changes coming", { count: behind })),
      ),
      h(CommitList, { commits: raw.commits_behind }),
      h(
        "button",
        { type: "button", className: "oui-btn oui-btn--primary oui-btn--block", disabled: printing || update.busy, onClick: () => open(() => updates.askUpdate(component)) },
        h(Icons.Download, { size: 18 }),
        tx("Update KlippEye"),
      ),
      printing && h("p", { className: "set-group__note set-group__note--warn" }, tx("A print is running: update when it finishes (the backend restarts).")),
      !printing && h("p", { className: "set-group__note" }, tx("The backend restarts for a few seconds and the page reloads by itself. Your settings stay.")),
    );
  }
  return h("div", { className: "set-status set-status--ok" }, h("span", { className: "set-status__dot" }), tx("KlippEye is up to date") + (update.checkedAt ? tx(" • checked at {time}", { time: new Date(update.checkedAt).toLocaleTimeString(LOCALE, { hour: "2-digit", minute: "2-digit" }) }) : ""));
}

function SoftwarePage({ active, menu, updates, printing, actions }) {
  const version = useBrainVersion(active);
  const update = useProgramUpdate(active);
  const channel = useUpdateChannel(active, () => update.check());
  const remoteRelease = useRemoteRelease(update.raw);
  const app = useAppRelease(active);
  const [services, setServices] = useState(null);
  useEffect(() => {
    if (!active) return undefined;
    let cancelled = false;
    loadServices()
      .then((list) => !cancelled && setServices(list.map((service) => service.name)))
      .catch(noop);
    return () => {
      cancelled = true;
    };
  }, [active]);

  if (version.state === "loading") return h("div", { className: "set-status" }, h("span", { className: "set-status__dot" }), tx("Checking the backend…"));
  if (version.state === "old" || version.state === "down") {
    return h(
      React.Fragment,
      null,
      h(
        "div",
        { className: "set-status set-status--warn" },
        h("span", { className: "set-status__dot" }),
        version.state === "old"
          ? h("span", null, tx("The backend on the Raspberry is older than 1.0: it cannot update itself from the dashboard. Install KlippEye 1.0 once with"), " ", h("code", null, INSTALL_COMMAND), " (", tx("guide:"), " ", h("code", null, tx("docs/GUIDE.md")), ").")
          : tx("The backend does not answer: if the printer works, restart it from Mainsail (Services → klippeye)."),
      ),
      h(InfoLine, { label: tx("Dashboard (this page)"), value: dashboardRelease() }),
    );
  }

  const info = version.info;
  const differs = releasesDiffer(info.release);
  const legacy = info.legacy === true;
  const git = info.git;
  const notifier = notifierService(services);
  return h(
    React.Fragment,
    null,
    h(
      SettingsGroup,
      { title: txc("software", "Installed") },
      h(
        "div",
        { className: "oui-list set-info-list" },
        h(InfoLine, { label: "Release", value: info.release }),
        h(InfoLine, { label: tx("Dashboard (this page)"), value: dashboardRelease(), warn: differs }),
        git && h(InfoLine, { label: tx("Code version"), value: git.commit + (git.branch ? " • " + git.branch : "") }),
        h(InfoLine, { label: tx("Backend up for"), value: formatUptime(info.uptime) }),
        Number(info.api) < BRAIN_API_LEVEL && h(InfoLine, { label: tx("Backend interface"), value: tx("{api} ({needed} needed)", { api: info.api, needed: BRAIN_API_LEVEL }), warn: true }),
      ),
      differs &&
        h(
          "div",
          { className: "set-status set-status--warn" },
          h("span", { className: "set-status__dot" }),
          h("span", null, tx("This page is "), h("b", null, dashboardRelease()), tx(" but the backend is "), h("b", null, info.release), tx(": reload it to get the new one. ")),
          h("button", { type: "button", className: "oui-btn oui-btn--sm", onClick: () => location.reload() }, tx("Reload")),
        ),
    ),
    legacy && h(MigrationBlock, { printing }),
    h(
      SettingsGroup,
      { title: txc("noun", "Update") },
      h(UpdateBlock, { update, remoteRelease, brainRelease: info.release, printing, menu, updates }),
      h(
        "button",
        { type: "button", className: "oui-btn oui-btn--block", disabled: update.checking || update.phase === "down", onClick: update.check },
        h(Icons.Refresh, { size: 18 }),
        update.checking ? tx("Checking on GitHub…") : tx("Check for a new release"),
      ),
      update.phase === "ok" &&
        update.raw.rollback_version &&
        update.raw.rollback_version !== update.raw.version &&
        h(
          "button",
          {
            type: "button",
            className: "oui-btn oui-btn--quiet oui-btn--block",
            onClick: () => {
              menu.close();
              updates.askRollback({ ...describeComponent(PROGRAM_COMPONENT, update.raw), raw: update.raw });
            },
          },
          h(Icons.Undo, { size: 18 }),
          tx("Go back to the previous release"),
        ),
    ),
    h(ChannelBlock, { channel, printing }),
    h(
      SettingsGroup,
      { title: tx("Android app"), note: tx("GitHub builds the app when you upload the android/ folder; it reaches the Raspberry with «Update KlippEye» and from here you install it on the phone.") },
      h(AppBlock, { app, installed: readInstalledApp() }),
    ),
    h(
      SettingsGroup,
      { title: txc("noun", "Restart"), note: tx("Restarting the backend takes a few seconds and the page reconnects by itself. A running print does not stop (Klipper drives it, not the backend); the AI monitor and the notifications stop only for a moment.") },
      h(
        "div",
        { className: "oui-list" },
        h(FileActionRow, { icon: h(Icons.RotateCw), title: tx("Restart the backend"), subtitle: tx("Dashboard, AI monitor and link to Moonraker"), onClick: () => actions.restartService(PROGRAM_COMPONENT) }),
        notifier && h(FileActionRow, { icon: h(Icons.Bell), title: tx("Restart the notifications"), subtitle: tx("The service that sends the alerts to the phone"), onClick: () => actions.restartService(notifier) }),
      ),
    ),
    h(
      SettingsGroup,
      { title: tx("Diagnostics"), note: tx("Release, services, Moonraker, settings and the last lines of the logs in one text file, to share when asking for help. Keys, password and tokens are never included.") },
      h(
        "div",
        { className: "oui-list" },
        h(FileActionRow, {
          icon: h(Icons.Download),
          title: tx("Download a diagnostic report"),
          subtitle: tx("The same as  klippeye diagnose  on the Raspberry"),
          onClick: () => downloadFile("/api/diagnose", "klippeye-diagnose.txt"),
        }),
      ),
    ),
  );
}

/* ---------------------------------------------------------------------------
   The move from VzBot to KlippEye
   An install made by VzBot 1.0.x still lives in ~/vzbot with the services "vzbot" and "vzbot-notifier"; the backend says so
   (/api/version: legacy). The button runs scripts/passa-a-klippeye.sh through the backend (/api/migrate/start), which copies
   the data, moves the program to ~/klippeye and installs the new services, and the block follows its steps
   (/api/migrate/status). The backend is away while the services change, then comes back as KlippEye.
   ------------------------------------------------------------------------- */
const MIGRATION_POLL_MS = 2000;
const MIGRATION_LIMIT_MS = 600000;
const MIGRATION_RELOAD_MS = 2500;

async function readMigrationStatus() {
  try {
    const response = await fetchFresh("/api/migrate/status", { timeout: BRAIN_READ_TIMEOUT_MS });
    if (!response.ok) return null;
    const data = await response.json();
    return isPlainObject(data) ? data : null;
  } catch (error) {
    return null;
  }
}

function MigrationBlock({ printing }) {
  // stage: "idle" | "confirm" | "starting" | "running" | "done" | "error" | "nosudo"
  const [stage, setStage] = useState("idle");
  const [status, setStatus] = useState({ step: 0, steps: 6, message: "" });
  const [problem, setProblem] = useState({ message: "", command: "" });
  const [lost, setLost] = useState(false); // the backend does not answer (it is being replaced)
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    readMigrationStatus().then((data) => {
      if (!alive.current || !data) return;
      if (data.state === "running") {
        setStatus({ step: Number(data.step) || 0, steps: Number(data.steps) || 6, message: String(data.message || "") });
        setStage("running");
      } else if (data.state === "error") setProblem({ message: tx("The last attempt failed: ") + String(data.message || ""), command: String(data.command || "") });
    });
    return () => {
      alive.current = false;
    };
  }, []);

  useEffect(() => {
    if (stage !== "running") return undefined;
    const began = Date.now();
    let timer = 0;
    const tick = async () => {
      const data = await readMigrationStatus();
      if (!alive.current) return;
      setLost(!data);
      if (data) {
        setStatus({ step: Number(data.step) || 0, steps: Number(data.steps) || 6, message: String(data.message || "") });
        if (data.state === "done") {
          // the backend is the new one now, and so is its page. Not tied to this block: once the new backend answers, the
          // block is gone (it is no longer "legacy") and a timer of its own would be cancelled with it.
          setTimeout(() => location.reload(), MIGRATION_RELOAD_MS);
          return setStage("done");
        }
        if (data.state === "error") {
          setProblem({ message: String(data.message || tx("unknown error")), command: String(data.command || "") });
          setStage("error");
          return;
        }
      }
      if (Date.now() - began > MIGRATION_LIMIT_MS) {
        setProblem({ message: tx("The backend has not answered for ten minutes. Check from the terminal with: klippeye status"), command: "" });
        setStage("error");
        return;
      }
      timer = setTimeout(tick, MIGRATION_POLL_MS);
    };
    timer = setTimeout(tick, MIGRATION_POLL_MS);
    return () => clearTimeout(timer);
  }, [stage]);

  const start = async () => {
    setStage("starting");
    const reply = await brainPost("/api/migrate/start", {});
    if (!alive.current) return;
    if (reply.ok) {
      setStatus({ step: 0, steps: 6, message: tx("Starting…") });
      setProblem({ message: "", command: "" });
      return setStage("running");
    }
    const command = reply.data && reply.data.command ? String(reply.data.command) : "";
    if (reply.data && reply.data.error === "no_sudo") {
      setProblem({ message: "", command });
      return setStage("nosudo");
    }
    setProblem({ message: reply.message || tx("the backend does not answer"), command });
    setStage("error");
  };

  const note = (text) => h("p", { className: "set-group__note" }, text);
  const command = (text) => h("div", { className: "oui-well set-command" }, h("code", null, text));
  let body;
  if (stage === "running" || stage === "done") {
    const percent = stage === "done" ? 100 : Math.round((Math.min(status.step, status.steps) / status.steps) * 100);
    body = h(
      React.Fragment,
      null,
      h("div", { className: "set-status set-status--update", role: "status" }, h("span", { className: "set-status__dot" }), h("span", null, stage === "done" ? status.message || tx("Done: you are now on KlippEye.") : tx("Step {step} of {steps}", { step: Math.max(1, status.step), steps: status.steps }) + (status.message ? ": " + status.message : ""))),
      h("div", { className: "oui-progress set-progress", role: "progressbar", "aria-valuemin": 0, "aria-valuemax": 100, "aria-valuenow": percent }, h("div", { className: "oui-progress__bar", style: { width: percent + "%" } })),
      note(stage === "done" ? tx("The page reloads by itself.") : lost ? tx("The backend is restarting with the new name: the page reconnects by itself. Do not turn off the Raspberry.") : tx("Do not close the menu and do not turn off the Raspberry: it takes about a minute.")),
    );
  } else if (stage === "nosudo") {
    body = h(React.Fragment, null, h("div", { className: "set-status set-status--warn", role: "alert" }, h("span", { className: "set-status__dot" }), h("span", null, tx("It cannot be done from here (it needs the administrator password). Connect to the Raspberry (SSH) and run this command:"))), command(problem.command || "bash ~/vzbot/scripts/passa-a-klippeye.sh"));
  } else if (stage === "error") {
    body = h(
      React.Fragment,
      null,
      h("div", { className: "set-status set-status--warn", role: "alert" }, h("span", { className: "set-status__dot" }), h("span", null, problem.message || tx("The move did not succeed."))),
      problem.command && note(tx("If that is not enough, from the terminal:")),
      problem.command && command(problem.command),
      h("button", { type: "button", className: "oui-btn oui-btn--block", onClick: () => setStage("idle") }, h(Icons.RotateCw, { size: 18 }), tx("Retry")),
    );
  } else if (stage === "confirm") {
    body = h(
      React.Fragment,
      null,
      note(tx("The program moves from ~/vzbot to ~/klippeye and the services vzbot and vzbot-notifier become klippeye and klippeye-notifier. Settings, AI key and notifications are copied (the originals stay where they are). The backend restarts for a moment; a running print does not stop, but it is better to do it with the printer idle.")),
      h("div", { className: "oui-btn-row" }, h("button", { type: "button", className: "oui-btn", onClick: () => setStage("idle") }, tx("Cancel")), h("button", { type: "button", className: "oui-btn oui-btn--primary", "data-migrate": "confirm", onClick: start }, tx("Move to KlippEye"))),
    );
  } else {
    body = h(
      React.Fragment,
      null,
      problem.message && h("div", { className: "set-status set-status--warn", role: "alert" }, h("span", { className: "set-status__dot" }), h("span", null, problem.message)),
      h("div", { className: "set-status set-status--update" }, h("span", { className: "set-status__dot" }), h("span", null, tx("This Raspberry still uses the VzBot names (folder ~/vzbot, service vzbot)."))),
      h("button", { type: "button", className: "oui-btn oui-btn--primary oui-btn--block", "data-migrate": "start", disabled: printing || stage === "starting", onClick: () => setStage("confirm") }, h(Icons.Rocket, { size: 18 }), stage === "starting" ? tx("Starting…") : tx("Move to KlippEye")),
      printing ? h("p", { className: "set-group__note set-group__note--warn" }, tx("A print is running: do it when it finishes.")) : note(tx("One step only, about a minute. After it, updates and commands use the new names (klippeye).")),
    );
  }
  return h(SettingsGroup, { title: tx("Move to KlippEye") }, body);
}

/** One line for the menu list: the release, and a sign when a newer one is waiting (KlippEye first, else the Android app). */
function softwareSummary(version, update, appWaiting) {
  if (version.state === "old") return tx("Backend to update");
  if (version.state === "down") return tx("Backend not reachable");
  if (version.state !== "ok") return tx("Release and updates");
  if (version.info.legacy === true) return tx("Move to KlippEye available");
  const waiting = update.phase === "ok" && Number(update.raw.commits_behind_count) > 0;
  return "Release " + version.info.release + (waiting ? tx(" • update available") : appWaiting ? tx(" • app to update") : "");
}
