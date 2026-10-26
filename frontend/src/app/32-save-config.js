/* ============================================================================
   32 · SAVE_CONFIG
   The header's save button asks for confirmation, then sends SAVE_CONFIG to
   Klipper (which writes the config and restarts the firmware).
   ========================================================================== */

const SAVE_BUTTON_DIM_MS = 2000;
const SAVE_TOAST_MS = 3000;

/** `onRestart()` is called when SAVE_CONFIG is sent: Klipper is about to restart (the state panel shows the ring at once). */
function useSaveConfig(onRestart = noop) {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const confirm = () => {
    setBusy(true);
    fireGcode("SAVE_CONFIG");
    moonraker.saveConfig().catch(noop);
    toast.notice(tx("SAVE_CONFIG sent - restarting..."), SAVE_TOAST_MS);
    onRestart();
    setDialogOpen(false);
    setTimeout(() => setBusy(false), SAVE_BUTTON_DIM_MS);
  };

  return { dialogOpen, busy, open: () => setDialogOpen(true), close: () => setDialogOpen(false), confirm };
}

function SaveConfigDialog({ open, onConfirm, onCancel }) {
  return h(ConfirmDialog, {
    open,
    tone: "neutral",
    icon: h(Icons.Save),
    title: "SAVE_CONFIG",
    subtitle: tx("Save configuration"),
    message: [
      tx("This will run "),
      h("code", { key: "cmd" }, "SAVE_CONFIG"),
      tx(" — Klipper will save the configuration and restart the firmware. Confirm?"),
    ],
    confirmLabel: tx("Save"),
    onConfirm,
    onCancel,
  });
}
