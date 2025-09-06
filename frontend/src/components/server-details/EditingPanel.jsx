import React from 'react';
import { FaSave } from 'react-icons/fa';

export default function EditingPanel({ editPath, editContent, setEditContent, onSave, onCancel }) {
  return (
    <div className="mt-4">
      <div className="text-xs text-white/70 mb-1">Editing: {editPath}</div>
      <textarea
        className="w-full h-40 rounded bg-black/40 border border-white/10 p-2 text-xs"
        value={editContent}
        onChange={(e) => setEditContent(e.target.value)}
      />
      <div className="mt-2 flex gap-2">
        <button
          onClick={onSave}
          className="rounded bg-brand-500 hover:bg-brand-400 px-3 py-1.5 inline-flex items-center gap-2 text-xs"
        >
          <FaSave /> Save
        </button>
        <button
          onClick={onCancel}
          className="rounded bg-white/10 hover:bg-white/20 px-3 py-1.5 text-xs"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

