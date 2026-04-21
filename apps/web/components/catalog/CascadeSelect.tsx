"use client";

import { C } from "@/lib/theme";
import { iS } from "@/components/ui";
import type { Category } from "./types";

export function CascadeSelect({
  categories, value, onChange, disabled,
}: {
  categories: Category[];
  value: number | "";
  onChange: (v: number | "") => void;
  disabled?: boolean;
}) {
  // Build tree helpers
  const roots = categories.filter(c => !c.parent_id);
  const childrenOf = (pid: number) => categories.filter(c => c.parent_id === pid);

  // Walk up to find the chain: [root, child, grandchild, ...]
  const getChain = (id: number | ""): number[] => {
    if (id === "") return [];
    const chain: number[] = [];
    let cur: Category | undefined = categories.find(c => c.id === id);
    while (cur) {
      chain.unshift(cur.id);
      cur = cur.parent_id ? categories.find(c => c.id === cur!.parent_id) : undefined;
    }
    return chain;
  };

  const chain = getChain(value);

  // Build levels: level 0 = roots, level 1 = children of chain[0], etc.
  const levels: { parentId: number | null; options: Category[]; selected: number | "" }[] = [];

  // Level 0: roots
  levels.push({ parentId: null, options: roots, selected: chain[0] ?? "" });

  // Subsequent levels based on selected chain
  for (let i = 0; i < chain.length; i++) {
    const kids = childrenOf(chain[i]);
    if (kids.length > 0) {
      levels.push({
        parentId: chain[i],
        options: kids,
        selected: chain[i + 1] ?? "",
      });
    }
  }

  const labels = ["Categoría", "Subcategoría", "Familia", "Subfamilia", "Nivel 5"];

  const handleChange = (levelIdx: number, newVal: number | "") => {
    if (newVal === "") {
      // Cleared this level — use parent as the selected category
      if (levelIdx === 0) {
        onChange("");
      } else {
        onChange(chain[levelIdx - 1]);
      }
    } else {
      onChange(newVal);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {levels.map((lvl, i) => (
        <div key={i} style={{ display: "flex", alignItems: "center", gap: 6 }}>
          {i > 0 && <span style={{ fontSize: 10, color: C.mute, marginLeft: i * 8 }}>{"↳"}</span>}
          <select
            value={lvl.selected}
            onChange={e => handleChange(i, e.target.value ? Number(e.target.value) : "")}
            style={{ ...iS, flex: 1 }}
            disabled={disabled}
          >
            <option value="">{i === 0 ? "Sin categoría" : `Sin ${labels[i] || "subcategoría"}`}</option>
            {lvl.options.map(c => (
              <option key={c.id} value={c.id}>{c.name}{c.code ? ` (${c.code})` : ""}</option>
            ))}
          </select>
        </div>
      ))}
      {levels.length > 0 && value !== "" && (
        <div style={{ fontSize: 10, color: C.mute }}>
          {getChain(value).map(id => categories.find(c => c.id === id)?.name).join(" → ")}
        </div>
      )}
    </div>
  );
}
