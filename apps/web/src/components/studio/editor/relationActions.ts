"use client";

import { defaultSafeColumns } from "@/lib/pickColumns";
import type { RelationDraft, TableInfo } from "@/lib/types";
import { slugify, type EditorCore } from "./useEditorCore";

export function relationActions(c: EditorCore) {
  const { tables, selected, endpoint, setStatus, updateEndpoint } = c;

  function addRelation(child: TableInfo) {
    if (!endpoint) return;
    const parentName = selected?.name ?? endpoint.table;
    const fk = child.foreign_keys.find((f) => f.ref_table === parentName);
    if (!fk) {
      setStatus(null, `${child.name} does not reference ${parentName}`);
      return;
    }
    const relName = slugify(child.name);
    if (endpoint.relations?.some((r) => r.name === relName)) {
      setStatus(null, `Relation '${relName}' already exists.`);
      return;
    }
    const fields = defaultSafeColumns(child);
    const rel: RelationDraft = {
      name: relName,
      table: child.name,
      schema: child.schema,
      type: "one_to_many",
      local_key: fk.ref_column || endpoint.primary_key,
      foreign_key: fk.column,
      fields,
      primary_key: child.primary_keys[0] ?? fields[0] ?? "id",
      max_per_parent: 50,
    };
    updateEndpoint({ relations: [...(endpoint.relations ?? []), rel] });
    setStatus(`Added nested array '${relName}' on ${endpoint.path}`);
  }

  function addManyToOne(fk: { column: string; ref_table: string; ref_column: string }) {
    if (!endpoint) return;
    const target = tables.find((t) => t.name === fk.ref_table);
    if (!target) {
      setStatus(null, `Table ${fk.ref_table} not in introspected schema.`);
      return;
    }
    const relName = slugify(fk.ref_table);
    if (endpoint.relations?.some((r) => r.name === relName)) {
      setStatus(null, `Relation '${relName}' already exists.`);
      return;
    }
    const fields = defaultSafeColumns(target);
    const rel: RelationDraft = {
      name: relName,
      table: target.name,
      schema: target.schema,
      type: "many_to_one",
      local_key: fk.column,
      foreign_key: fk.ref_column || target.primary_keys[0] || "id",
      fields,
      primary_key: target.primary_keys[0] ?? fields[0] ?? "id",
      max_per_parent: 1,
    };
    updateEndpoint({ relations: [...(endpoint.relations ?? []), rel] });
    setStatus(`Added nested object '${relName}' on ${endpoint.path}`);
  }

  function updateRelation(name: string, patch: Partial<RelationDraft>) {
    if (!endpoint) return;
    updateEndpoint({
      relations: (endpoint.relations ?? []).map((r) =>
        r.name === name ? { ...r, ...patch } : r,
      ),
    });
  }

  function toggleRelationField(relName: string, field: string) {
    if (!endpoint) return;
    const rel = (endpoint.relations ?? []).find((r) => r.name === relName);
    if (!rel) return;
    const set = new Set(rel.fields);
    if (set.has(field)) {
      if (field === rel.primary_key || field === rel.foreign_key) return;
      if (set.size <= 1) return;
      set.delete(field);
    } else {
      set.add(field);
    }
    updateRelation(relName, { fields: [...set] });
  }

  function removeRelation(name: string) {
    if (!endpoint) return;
    updateEndpoint({
      relations: (endpoint.relations ?? []).filter((r) => r.name !== name),
    });
  }

  return { addRelation, addManyToOne, updateRelation, toggleRelationField, removeRelation };
}
