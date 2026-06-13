import { Button, Modal } from '../../../components/primitives';

// The second confirmation gate for a destructive or deploy action. The first action opens
// this; only Confirm here carries it out.
export function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel,
  onConfirm,
  onCancel,
  busy = false,
}: {
  open: boolean;
  title: string;
  body: string;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
  busy?: boolean;
}) {
  return (
    <Modal open={open} title={title} onClose={onCancel}>
      <p className="mb-4 text-sm text-muted">{body}</p>
      <div className="flex justify-end gap-2">
        <Button variant="muted" onClick={onCancel} disabled={busy}>
          Cancel
        </Button>
        <Button variant="primary" onClick={onConfirm} disabled={busy}>
          {busy ? 'Working' : confirmLabel}
        </Button>
      </div>
    </Modal>
  );
}
