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
  return seconds > 0 ? new Date(seconds * 1000).toLocaleDateString("it-IT", { day: "2-digit", month: "short" }) : "";
};

/** The address of the VERSION file of the repository Moonraker updates from, on raw.githubusercontent.com; "" when that is not GitHub. */
function remoteVersionUrl(info) {
  const url = String((info && (info.remote_url || info.recovery_url)) || "");
  const match = /github\.com[:/]([^/]+)\/([^/]+?)(?:\.git)?\/?$/.exec(url);
  if (!match) return "";
  const branch = String((info && info.branch) || "main").replace(/[^A-Za-z0-9._/-]/g, "");
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
    list.map((commit, index) => h("li", { key: commit.sha || index }, h("span", { className: "set-commits__subject" }, commit.subject || "(senza descrizione)"), h("span", { className: "set-commits__date" }, formatCommitDate(commit.date)))),
    more > 0 && h("li", { className: "set-commits__more" }, "e altre " + more + " modifiche"),
  );
}

/** The state of Moonraker's side: what it says about the repository, and the buttons that follow from it. */
function UpdateBlock({ update, remoteRelease, brainRelease, printing, menu, updates }) {
  const { phase, raw } = update;
  if (phase === "loading") return h("div", { className: "set-status" }, h("span", { className: "set-status__dot" }), "Chiedo a Moonraker se c'è qualcosa di nuovo…");
  if (phase === "down") return h("div", { className: "set-status set-status--warn" }, h("span", { className: "set-status__dot" }), "Moonraker non risponde: non posso sapere se ci sono aggiornamenti.");
  if (phase === "missing") {
    return h(
      "div",
      { className: "set-status set-status--warn" },
      h("span", { className: "set-status__dot" }),
      h("span", null, "Moonraker non conosce ancora KlippEye tra i programmi aggiornabili. Sul Raspberry lancia ", h("code", null, INSTALL_COMMAND), " (lo collega) e poi riavvia Moonraker dal menu Riavvia."),
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
    const why = (Array.isArray(raw.warnings) && raw.warnings.length ? raw.warnings.join(" ") : "") || (raw.is_dirty ? "Qualche file del programma sul Raspberry è stato modificato a mano." : "Il repository del programma sul Raspberry non è in ordine.");
    return h(
      React.Fragment,
      null,
      h("div", { className: "set-status set-status--warn", role: "alert" }, h("span", { className: "set-status__dot" }), h("span", null, why + " Finché è così Moonraker rifiuta di aggiornare.")),
      h("button", { type: "button", className: "oui-btn oui-btn--block", onClick: () => open(() => updates.askRecover(component)) }, h(Icons.RotateCw, { size: 18 }), "Ripristina i file del programma"),
      h("p", { className: "set-group__note" }, "Riporta i file alla versione ufficiale. Impostazioni, chiave dell'IA e notifiche stanno in un'altra cartella e non si toccano."),
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
        h("span", null, remoteRelease ? "Disponibile la release " + remoteRelease + (brainRelease ? " (ora hai la " + brainRelease + ")" : "") : "Aggiornamento disponibile: " + behind + (behind === 1 ? " modifica" : " modifiche") + " in arrivo"),
      ),
      h(CommitList, { commits: raw.commits_behind }),
      h(
        "button",
        { type: "button", className: "oui-btn oui-btn--primary oui-btn--block", disabled: printing || update.busy, onClick: () => open(() => updates.askUpdate(component)) },
        h(Icons.Download, { size: 18 }),
        "Aggiorna KlippEye",
      ),
      printing && h("p", { className: "set-group__note set-group__note--warn" }, "C'è una stampa in corso: aggiorna quando finisce (il backend si riavvia)."),
      !printing && h("p", { className: "set-group__note" }, "Il backend si riavvia per qualche secondo e la pagina si ricarica da sola. Le tue impostazioni restano."),
    );
  }
  return h("div", { className: "set-status set-status--ok" }, h("span", { className: "set-status__dot" }), "KlippEye è aggiornato" + (update.checkedAt ? " • controllato alle " + new Date(update.checkedAt).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" }) : ""));
}

function SoftwarePage({ active, menu, updates, printing, actions }) {
  const version = useBrainVersion(active);
  const update = useProgramUpdate(active);
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

  if (version.state === "loading") return h("div", { className: "set-status" }, h("span", { className: "set-status__dot" }), "Controllo il backend…");
  if (version.state === "old" || version.state === "down") {
    return h(
      React.Fragment,
      null,
      h(
        "div",
        { className: "set-status set-status--warn" },
        h("span", { className: "set-status__dot" }),
        version.state === "old"
          ? h("span", null, "Il backend sul Raspberry è una versione precedente alla 1.0: non sa aggiornarsi dalla dashboard. Installa KlippEye 1.0 una volta sola con ", h("code", null, INSTALL_COMMAND), " (guida: ", h("code", null, "docs/GUIDA.md"), ").")
          : "Il backend non risponde: se la stampante funziona, riavvialo da Mainsail (Servizi → klippeye).",
      ),
      h(InfoLine, { label: "Dashboard (questa pagina)", value: dashboardRelease() }),
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
      { title: "Installato" },
      h(
        "div",
        { className: "oui-list set-info-list" },
        h(InfoLine, { label: "Release", value: info.release }),
        h(InfoLine, { label: "Dashboard (questa pagina)", value: dashboardRelease(), warn: differs }),
        git && h(InfoLine, { label: "Versione del codice", value: git.commit + (git.branch ? " • " + git.branch : "") }),
        h(InfoLine, { label: "Backend acceso da", value: formatUptime(info.uptime) }),
        Number(info.api) < BRAIN_API_LEVEL && h(InfoLine, { label: "Interfaccia del backend", value: info.api + " (serve la " + BRAIN_API_LEVEL + ")", warn: true }),
      ),
      differs &&
        h(
          "div",
          { className: "set-status set-status--warn" },
          h("span", { className: "set-status__dot" }),
          h("span", null, "Questa pagina è la ", h("b", null, dashboardRelease()), " ma il backend è la ", h("b", null, info.release), ": ricaricala per avere quella nuova. "),
          h("button", { type: "button", className: "oui-btn oui-btn--sm", onClick: () => location.reload() }, "Ricarica"),
        ),
    ),
    legacy && h(MigrationBlock, { printing }),
    h(
      SettingsGroup,
      { title: "Aggiornamento" },
      h(UpdateBlock, { update, remoteRelease, brainRelease: info.release, printing, menu, updates }),
      h(
        "button",
        { type: "button", className: "oui-btn oui-btn--block", disabled: update.checking || update.phase === "down", onClick: update.check },
        h(Icons.Refresh, { size: 18 }),
        update.checking ? "Controllo su GitHub…" : "Controlla se c'è una versione nuova",
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
          "Torna alla versione precedente",
        ),
    ),
    h(
      SettingsGroup,
      { title: "App Android", note: "GitHub costruisce l'app quando carichi la cartella android/; arriva sul Raspberry con «Aggiorna KlippEye» e da qui la installi sul telefono." },
      h(AppBlock, { app, installed: readInstalledApp() }),
    ),
    h(
      SettingsGroup,
      { title: "Riavvio", note: "Il riavvio del backend dura qualche secondo e la pagina si ricollega da sola. Una stampa in corso non si ferma (la guida Klipper, non il backend); il monitor IA e le notifiche si fermano solo per un momento." },
      h(
        "div",
        { className: "oui-list" },
        h(FileActionRow, { icon: h(Icons.RotateCw), title: "Riavvia il backend", subtitle: "Dashboard, monitor IA e collegamento con Moonraker", onClick: () => actions.restartService(PROGRAM_COMPONENT) }),
        notifier && h(FileActionRow, { icon: h(Icons.Bell), title: "Riavvia le notifiche", subtitle: "Il servizio che manda gli avvisi al telefono", onClick: () => actions.restartService(notifier) }),
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
      } else if (data.state === "error") setProblem({ message: "L'ultimo tentativo non è riuscito: " + String(data.message || ""), command: String(data.command || "") });
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
          setProblem({ message: String(data.message || "errore sconosciuto"), command: String(data.command || "") });
          setStage("error");
          return;
        }
      }
      if (Date.now() - began > MIGRATION_LIMIT_MS) {
        setProblem({ message: "Il backend non risponde da dieci minuti. Controlla dal terminale con: klippeye stato", command: "" });
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
      setStatus({ step: 0, steps: 6, message: "Parto…" });
      setProblem({ message: "", command: "" });
      return setStage("running");
    }
    const command = reply.data && reply.data.command ? String(reply.data.command) : "";
    if (reply.data && reply.data.error === "no_sudo") {
      setProblem({ message: "", command });
      return setStage("nosudo");
    }
    setProblem({ message: reply.message || "il backend non risponde", command });
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
      h("div", { className: "set-status set-status--update", role: "status" }, h("span", { className: "set-status__dot" }), h("span", null, stage === "done" ? status.message || "Fatto: ora sei su KlippEye." : "Passo " + Math.max(1, status.step) + " di " + status.steps + (status.message ? ": " + status.message : ""))),
      h("div", { className: "oui-progress set-progress", role: "progressbar", "aria-valuemin": 0, "aria-valuemax": 100, "aria-valuenow": percent }, h("div", { className: "oui-progress__bar", style: { width: percent + "%" } })),
      note(stage === "done" ? "La pagina si ricarica da sola." : lost ? "Il backend si sta riavviando con il nuovo nome: la pagina si ricollega da sola. Non spegnere il Raspberry." : "Non chiudere il menu e non spegnere il Raspberry: ci vuole circa un minuto."),
    );
  } else if (stage === "nosudo") {
    body = h(React.Fragment, null, h("div", { className: "set-status set-status--warn", role: "alert" }, h("span", { className: "set-status__dot" }), h("span", null, "Da qui non posso farlo da solo (serve la password di amministratore). Collegati al Raspberry (SSH) e lancia questo comando:")), command(problem.command || "bash ~/vzbot/scripts/passa-a-klippeye.sh"));
  } else if (stage === "error") {
    body = h(
      React.Fragment,
      null,
      h("div", { className: "set-status set-status--warn", role: "alert" }, h("span", { className: "set-status__dot" }), h("span", null, problem.message || "Il passaggio non è riuscito.")),
      problem.command && note("Se non basta, da terminale:"),
      problem.command && command(problem.command),
      h("button", { type: "button", className: "oui-btn oui-btn--block", onClick: () => setStage("idle") }, h(Icons.RotateCw, { size: 18 }), "Riprova"),
    );
  } else if (stage === "confirm") {
    body = h(
      React.Fragment,
      null,
      note("Il programma si sposta da ~/vzbot a ~/klippeye e i servizi vzbot e vzbot-notifier diventano klippeye e klippeye-notifier. Impostazioni, chiave dell'IA e notifiche vengono copiate (gli originali restano dove sono). Il backend si riavvia per un momento; una stampa in corso non si ferma, ma è meglio farlo a stampante ferma."),
      h("div", { className: "oui-btn-row" }, h("button", { type: "button", className: "oui-btn", onClick: () => setStage("idle") }, "Annulla"), h("button", { type: "button", className: "oui-btn oui-btn--primary", "data-migrate": "confirm", onClick: start }, "Passa a KlippEye")),
    );
  } else {
    body = h(
      React.Fragment,
      null,
      problem.message && h("div", { className: "set-status set-status--warn", role: "alert" }, h("span", { className: "set-status__dot" }), h("span", null, problem.message)),
      h("div", { className: "set-status set-status--update" }, h("span", { className: "set-status__dot" }), h("span", null, "Questo Raspberry usa ancora i nomi di VzBot (cartella ~/vzbot, servizio vzbot).")),
      h("button", { type: "button", className: "oui-btn oui-btn--primary oui-btn--block", "data-migrate": "start", disabled: printing || stage === "starting", onClick: () => setStage("confirm") }, h(Icons.Rocket, { size: 18 }), stage === "starting" ? "Parto…" : "Passa a KlippEye"),
      printing ? h("p", { className: "set-group__note set-group__note--warn" }, "C'è una stampa in corso: fallo quando finisce.") : note("Un passaggio solo, circa un minuto. Dopo, gli aggiornamenti e i comandi usano i nuovi nomi (klippeye)."),
    );
  }
  return h(SettingsGroup, { title: "Passa a KlippEye" }, body);
}

/** One line for the menu list: the release, and a sign when a newer one is waiting (KlippEye first, else the Android app). */
function softwareSummary(version, update, appWaiting) {
  if (version.state === "old") return "Backend da aggiornare";
  if (version.state === "down") return "Backend non raggiungibile";
  if (version.state !== "ok") return "Release e aggiornamenti";
  if (version.info.legacy === true) return "Passaggio a KlippEye disponibile";
  const waiting = update.phase === "ok" && Number(update.raw.commits_behind_count) > 0;
  return "Release " + version.info.release + (waiting ? " • aggiornamento disponibile" : appWaiting ? " • app da aggiornare" : "");
}
