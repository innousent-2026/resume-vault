import { APPLICATION_STATUSES } from "../lib/api.js";

export default function StatusSelect({ value, onChange, disabled }) {
  return (
    <select
      className={`status-select ${value}`}
      value={value}
      disabled={disabled}
      onChange={(event) => onChange(event.target.value)}
    >
      {APPLICATION_STATUSES.map((status) => (
        <option key={status} value={status}>
          {status}
        </option>
      ))}
    </select>
  );
}
