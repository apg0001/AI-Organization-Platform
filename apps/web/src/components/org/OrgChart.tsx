/**
 * 조직도(React Flow). 설계 모드(명세 편집)와 운영 모드(실제 조직, 실시간 상태)가 같은 컴포넌트를 쓴다.
 *
 * - 노드 = 에이전트. 위·아래 손잡이 = 보고 관계(상위 → 하위), 좌·우 손잡이 = 협업 관계.
 * - 보고 관계는 실선, 협업은 점선(종류별 색·라벨). 색만으로 구분하지 않도록 선 모양과 라벨을 함께 쓴다.
 * - 위치는 dagre 자동 배치. 사용자가 끌어 옮긴 위치는 이 화면에서만 유지한다(명세에는 저장하지 않음).
 */

import "@xyflow/react/dist/style.css";

import dagre from "@dagrejs/dagre";
import {
  Background,
  BackgroundVariant,
  type Connection,
  Controls,
  type Edge,
  Handle,
  MarkerType,
  MiniMap,
  type Node,
  type NodeProps,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useNodesState,
  useReactFlow,
} from "@xyflow/react";
import { Crown, EllipsisVertical } from "lucide-react";
import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AgentAvatar } from "@/components/agent/AgentAvatar";
import { AgentStatus, DeptChip } from "@/components/common/states";
import { Menu, MenuContent, MenuItem, MenuLabel, MenuTrigger } from "@/components/ui/overlay";
import { PermissionBadges } from "@/features/permissions/PermissionParts";
import type { AgentPermissions, AgentStatus as Status, Organization, OrgSpec, SpecCollaboration } from "@/lib/api";
import { PRESETS, type PresetId } from "@/lib/permissions";
import { cn } from "@/lib/utils";

export const COLLAB_META: Record<SpecCollaboration["kind"], { label: string; color: string }> = {
  handoff: { label: "결과 전달", color: "var(--dept-2)" },
  review: { label: "검토 요청", color: "var(--dept-3)" },
  consult: { label: "자문", color: "var(--dept-6)" },
};

interface AgentNodeData extends Record<string, unknown> {
  agentKey: string;
  name: string;
  title: string;
  dept: { name: string; color: string } | null;
  lead: boolean;
  enabled: boolean;
  status?: Status;
  editable: boolean;
  suggestion: boolean;
  perms: AgentPermissions;
  /** 프리셋 메뉴(운영 모드에서만). 우클릭·컨텍스트 메뉴 키·노드 안의 버튼으로 연다. */
  menu: { open: boolean; onOpenChange: (open: boolean) => void; onPreset: (preset: PresetId, trigger: HTMLElement | null) => void } | null;
}

type AgentNode = Node<AgentNodeData, "agent">;

const NODE_W = 216;
const NODE_H = 94;

const AgentNodeView = memo(function AgentNodeView({ data, selected }: NodeProps<AgentNode>) {
  const handle = "!size-2.5 !border-border-strong !bg-surface-3";
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = data.menu;
  return (
    <div
      className={cn(
        "flex w-[216px] items-center gap-2.5 rounded-lg border bg-surface-1 px-2.5 py-2 transition-[border-color,box-shadow] duration-150",
        selected ? "border-primary-text shadow-[0_0_0_3px_var(--primary-soft)]" : "border-border-strong",
        !data.enabled && "opacity-55",
      )}
    >
      <Handle type="target" position={Position.Top} id="report-in" className={handle} isConnectable={data.editable} />
      <Handle type="target" position={Position.Left} id="collab-in" className={cn(handle, "!rounded-sm")} isConnectable={data.editable} />
      <AgentAvatar id={data.agentKey} lead={data.lead} size={36} dim={!data.enabled} />
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="flex items-center gap-1 truncate text-sm font-medium">
          {data.lead ? <Crown className="size-3.5 shrink-0 text-warning" aria-label="CEO" /> : null}
          <span className="min-w-0 flex-1 truncate">{data.name}</span>
          {menu ? (
            <Menu open={menu.open} onOpenChange={menu.onOpenChange}>
              <MenuTrigger asChild>
                {/* 노드 클릭(상세로 이동)·끌기·방향키 이동과 섞이지 않게 이벤트를 여기서 멈춘다. */}
                <button
                  ref={trigger}
                  type="button"
                  aria-label={`${data.name} 권한 프리셋`}
                  title="권한 프리셋(노드에서 우클릭·컨텍스트 메뉴 키로도 열림)"
                  className="nodrag nopan -my-0.5 -mr-1 shrink-0 cursor-pointer rounded-sm p-0.5 text-faint hover:bg-surface-3 hover:text-fg"
                  onClick={(e) => e.stopPropagation()}
                  onKeyDown={(e) => e.stopPropagation()}
                >
                  <EllipsisVertical className="size-3.5" aria-hidden />
                </button>
              </MenuTrigger>
              <MenuContent align="start" onClick={(e) => e.stopPropagation()} onKeyDown={(e) => e.stopPropagation()}>
                <MenuLabel>권한 프리셋</MenuLabel>
                {PRESETS.map((p) => (
                  <MenuItem key={p.id} title={p.description} onSelect={() => menu.onPreset(p.id, trigger.current)}>
                    {p.label}
                  </MenuItem>
                ))}
              </MenuContent>
            </Menu>
          ) : null}
        </span>
        <span className="truncate text-xs text-muted">{data.title || "직책 없음"}</span>
        <span className="flex items-center justify-between gap-2">
          {data.dept ? <DeptChip name={data.dept.name} color={data.dept.color} /> : <span className="text-2xs text-faint">부서 없음</span>}
          {data.status ? <AgentStatus status={data.status} compact /> : null}
          {data.suggestion ? (
            <span className="text-2xs text-warning" title="AI가 권한 확대를 제안했습니다(검토 필요)">
              권한 제안
            </span>
          ) : null}
        </span>
        <PermissionBadges perms={data.perms} />
      </div>
      <Handle type="source" position={Position.Bottom} id="report-out" className={handle} isConnectable={data.editable} />
      <Handle type="source" position={Position.Right} id="collab-out" className={cn(handle, "!rounded-sm")} isConnectable={data.editable} />
    </div>
  );
});

const nodeTypes = { agent: AgentNodeView };

export function orgAsSpec(org: Organization): OrgSpec {
  return {
    name: org.name,
    description: org.description,
    mission: org.mission,
    base_instructions: org.base_instructions,
    policy: {},
    departments: org.departments.map((d) => ({ key: d.id, name: d.name, description: d.description, color: d.color })),
    agents: org.agents.map((a) => ({
      key: a.id,
      name: a.name,
      title: a.title,
      department: a.department_id,
      role: a.role,
      responsibilities: a.responsibilities,
      expertise: a.expertise,
      instructions: a.instructions,
      reports_to: a.reports_to_id,
      is_lead: a.is_lead,
      enabled: a.enabled,
      permissions: a.permissions,
      permission_suggestion: null,
      recommended_skills: [],
      recommended_mcp: [],
      allowed_skills: a.allowed_skills,
      allowed_mcp_servers: a.allowed_mcp_servers,
      allowed_plugins: a.allowed_plugins,
      model: a.model,
    })),
    collaborations: org.collaborations.map((c) => ({
      source: c.source_agent_id,
      target: c.target_agent_id,
      kind: c.kind,
      label: c.label,
    })),
    workflows: [],
    recommended_skills: [],
    recommended_mcp: [],
  };
}

function layout(spec: OrgSpec): Record<string, { x: number; y: number }> {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: "TB", nodesep: 28, ranksep: 64, marginx: 20, marginy: 20 });
  g.setDefaultEdgeLabel(() => ({}));
  spec.agents.forEach((a) => g.setNode(a.key, { width: NODE_W, height: NODE_H }));
  spec.agents.forEach((a) => {
    if (a.reports_to) g.setEdge(a.reports_to, a.key);
  });
  dagre.layout(g);
  const out: Record<string, { x: number; y: number }> = {};
  spec.agents.forEach((a) => {
    const n = g.node(a.key);
    out[a.key] = { x: (n?.x ?? 0) - NODE_W / 2, y: (n?.y ?? 0) - NODE_H / 2 };
  });
  return out;
}

export interface OrgChartProps {
  spec: OrgSpec;
  statuses?: Record<string, Status>;
  selected?: string | null;
  onSelect?: (key: string | null) => void;
  /** 주면 편집 가능: 연결로 보고·협업 관계를 바꾼다. */
  onChange?: (next: OrgSpec) => void;
  /** 주면 노드에 권한 프리셋 메뉴가 생긴다(우클릭·컨텍스트 메뉴 키·노드 안 버튼). trigger는 확인 창 뒤 포커스를 돌려줄 버튼. */
  onPreset?: (key: string, preset: PresetId, trigger: HTMLElement | null) => void;
  layoutVersion?: number;
  className?: string;
}

export function OrgChart(props: OrgChartProps) {
  return (
    <ReactFlowProvider>
      <OrgChartInner {...props} />
    </ReactFlowProvider>
  );
}

function OrgChartInner({ spec, statuses, selected, onSelect, onChange, onPreset, layoutVersion = 0, className }: OrgChartProps) {
  const editable = Boolean(onChange);
  const [menuFor, setMenuFor] = useState<string | null>(null);
  // 노드 데이터가 매 렌더마다 바뀌지 않게 최신 콜백은 ref로 읽는다.
  const presetRef = useRef(onPreset);
  presetRef.current = onPreset;
  const hasPreset = Boolean(onPreset);
  const flow = useReactFlow();
  const structureKey = spec.agents.map((a) => `${a.key}>${a.reports_to ?? ""}`).join("|");
  const positions = useMemo(() => layout(spec), [structureKey, layoutVersion]); // eslint-disable-line react-hooks/exhaustive-deps
  const depts = useMemo(() => new Map(spec.departments.map((d) => [d.key, d])), [spec.departments]);

  const built: AgentNode[] = useMemo(
    () =>
      spec.agents.map((a) => {
        const dept = a.department ? depts.get(a.department) : undefined;
        return {
          id: a.key,
          type: "agent",
          position: positions[a.key] ?? { x: 0, y: 0 },
          selected: a.key === selected,
          data: {
            agentKey: a.key,
            name: a.name,
            title: a.title,
            dept: dept ? { name: dept.name, color: dept.color } : null,
            lead: a.is_lead,
            enabled: a.enabled,
            status: statuses?.[a.key],
            editable,
            suggestion: Boolean(a.permission_suggestion),
            perms: a.permissions,
            menu: hasPreset
              ? {
                  open: menuFor === a.key,
                  onOpenChange: (open: boolean) => setMenuFor((current) => (open ? a.key : current === a.key ? null : current)),
                  onPreset: (preset: PresetId, trigger: HTMLElement | null) => presetRef.current?.(a.key, preset, trigger),
                }
              : null,
          },
        };
      }),
    [spec.agents, depts, positions, statuses, selected, editable, hasPreset, menuFor],
  );
  const [nodes, setNodes, onNodesChange] = useNodesState<AgentNode>(built);
  useEffect(() => {
    // 구조가 같으면 사용자가 옮긴 위치를 유지하고 내용만 바꾼다.
    setNodes((current) => {
      const moved = new Map(current.map((n) => [n.id, n.position]));
      return built.map((n) => ({ ...n, position: moved.get(n.id) ?? n.position }));
    });
  }, [built, setNodes]);
  useEffect(() => {
    setNodes((current) => current.map((n) => ({ ...n, position: positions[n.id] ?? n.position })));
    window.requestAnimationFrame(() => void flow.fitView({ padding: 0.15, duration: 200 }));
  }, [positions, setNodes, flow]);

  const edges: Edge[] = useMemo(() => {
    const reports = spec.agents
      .filter((a) => a.reports_to)
      .map((a) => ({
        id: `r:${a.reports_to}:${a.key}`,
        source: a.reports_to!,
        target: a.key,
        sourceHandle: "report-out",
        targetHandle: "report-in",
        type: "smoothstep",
        style: { stroke: "var(--border-strong)", strokeWidth: 1.5 },
        deletable: editable,
      }));
    const collabs = spec.collaborations.map((c) => ({
      id: `c:${c.source}:${c.target}:${c.kind}`,
      source: c.source,
      target: c.target,
      sourceHandle: "collab-out",
      targetHandle: "collab-in",
      type: "default",
      label: c.label || COLLAB_META[c.kind].label,
      labelStyle: { fill: "var(--text-muted)", fontSize: 11 },
      labelBgStyle: { fill: "var(--surface-1)" },
      labelBgPadding: [4, 2] as [number, number],
      style: { stroke: COLLAB_META[c.kind].color, strokeDasharray: "5 4", strokeWidth: 1.25 },
      markerEnd: { type: MarkerType.ArrowClosed, color: COLLAB_META[c.kind].color, width: 14, height: 14 },
      deletable: editable,
    }));
    return [...reports, ...collabs];
  }, [spec.agents, spec.collaborations, editable]);

  const onConnect = useCallback(
    (c: Connection) => {
      if (!onChange || !c.source || !c.target || c.source === c.target) return;
      if (c.sourceHandle === "report-out" && c.targetHandle === "report-in") {
        // 순환이 생기면 무시한다(서버도 다시 검증한다).
        let cursor: string | null = c.source;
        const managers = new Map(spec.agents.map((a) => [a.key, a.reports_to]));
        while (cursor) {
          if (cursor === c.target) return;
          cursor = managers.get(cursor) ?? null;
        }
        onChange({
          ...spec,
          agents: spec.agents.map((a) => (a.key === c.target ? { ...a, reports_to: c.source } : a)),
        });
      } else if (c.sourceHandle === "collab-out" && c.targetHandle === "collab-in") {
        if (spec.collaborations.some((x) => x.source === c.source && x.target === c.target)) return;
        onChange({
          ...spec,
          collaborations: [...spec.collaborations, { source: c.source, target: c.target, kind: "handoff", label: "" }],
        });
      }
    },
    [onChange, spec],
  );

  const onEdgesDelete = useCallback(
    (removed: Edge[]) => {
      if (!onChange) return;
      const ids = new Set(removed.map((e) => e.id));
      onChange({
        ...spec,
        agents: spec.agents.map((a) =>
          a.reports_to && ids.has(`r:${a.reports_to}:${a.key}`) ? { ...a, reports_to: null } : a,
        ),
        collaborations: spec.collaborations.filter((c) => !ids.has(`c:${c.source}:${c.target}:${c.kind}`)),
      });
    },
    [onChange, spec],
  );

  return (
    <div className={cn("h-full min-h-0 w-full", className)}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onConnect={onConnect}
        onEdgesDelete={onEdgesDelete}
        onNodeClick={(_, node) => onSelect?.(node.id)}
        onNodeContextMenu={
          hasPreset
            ? (event, node) => {
                // 마우스 우클릭과 키보드(컨텍스트 메뉴 키·Shift+F10) 모두 이 이벤트로 온다.
                event.preventDefault();
                setMenuFor(node.id);
              }
            : undefined
        }
        onPaneClick={() => onSelect?.(null)}
        nodesConnectable={editable}
        edgesFocusable={editable}
        deleteKeyCode={editable ? ["Backspace", "Delete"] : null}
        fitView
        fitViewOptions={{ padding: 0.15 }}
        minZoom={0.25}
        maxZoom={1.75}
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={20} size={1} />
        <Controls showInteractive={false} position="bottom-left" />
        {spec.agents.length > 8 ? (
          <MiniMap pannable zoomable position="bottom-right" />
        ) : null}
      </ReactFlow>
    </div>
  );
}

export function ChartLegend() {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-2xs text-faint">
      <span className="flex items-center gap-1.5">
        <svg width="18" height="6" aria-hidden>
          <line x1="0" y1="3" x2="18" y2="3" stroke="var(--border-strong)" strokeWidth="1.5" />
        </svg>
        보고 관계(위 → 아래 손잡이)
      </span>
      {Object.entries(COLLAB_META).map(([kind, meta]) => (
        <span key={kind} className="flex items-center gap-1.5">
          <svg width="18" height="6" aria-hidden>
            <line x1="0" y1="3" x2="18" y2="3" stroke={meta.color} strokeWidth="1.5" strokeDasharray="4 3" />
          </svg>
          {meta.label}
        </span>
      ))}
      <span>협업은 오른쪽 → 왼쪽 손잡이를 끌어 연결</span>
    </div>
  );
}
