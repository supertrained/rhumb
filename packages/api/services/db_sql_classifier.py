"""Read-only SQL classification helpers for database capabilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from pglast import ast, parse_sql
from pglast.parser import ParseError


_DENIED_NODE_TYPES = {
    "AlterCollationStmt",
    "AlterDatabaseRefreshCollStmt",
    "AlterDatabaseSetStmt",
    "AlterDatabaseStmt",
    "AlterDefaultPrivilegesStmt",
    "AlterDomainStmt",
    "AlterEnumStmt",
    "AlterEventTrigStmt",
    "AlterExtensionContentsStmt",
    "AlterExtensionStmt",
    "AlterFdwStmt",
    "AlterForeignServerStmt",
    "AlterFunctionStmt",
    "AlterObjectDependsStmt",
    "AlterObjectSchemaStmt",
    "AlterOpFamilyStmt",
    "AlterOperatorStmt",
    "AlterOwnerStmt",
    "AlterPolicyStmt",
    "AlterPublicationStmt",
    "AlterRoleSetStmt",
    "AlterRoleStmt",
    "AlterSeqStmt",
    "AlterStatsStmt",
    "AlterSubscriptionStmt",
    "AlterSystemStmt",
    "AlterTSConfigurationStmt",
    "AlterTSDictionaryStmt",
    "AlterTableCmd",
    "AlterTableMoveAllStmt",
    "AlterTableSpaceOptionsStmt",
    "AlterTableStmt",
    "AlterUserMappingStmt",
    "CallStmt",
    "CheckpointStmt",
    "ClusterStmt",
    "CommentStmt",
    "CompositeTypeStmt",
    "CopyStmt",
    "CreateAmStmt",
    "CreateCastStmt",
    "CreateConversionStmt",
    "CreateDomainStmt",
    "CreateEnumStmt",
    "CreateEventTrigStmt",
    "CreateExtensionStmt",
    "CreateFdwStmt",
    "CreateForeignServerStmt",
    "CreateForeignTableStmt",
    "CreateFunctionStmt",
    "CreateOpClassItem",
    "CreateOpClassStmt",
    "CreateOpFamilyStmt",
    "CreatePLangStmt",
    "CreatePolicyStmt",
    "CreatePublicationStmt",
    "CreateRangeStmt",
    "CreateRoleStmt",
    "CreateSchemaStmt",
    "CreateSeqStmt",
    "CreateStatsStmt",
    "CreateStmt",
    "CreateSubscriptionStmt",
    "CreateTableAsStmt",
    "CreateTransformStmt",
    "CreateTrigStmt",
    "CreatedbStmt",
    "DeallocateStmt",
    "DeclareCursorStmt",
    "DeleteStmt",
    "DiscardStmt",
    "DoStmt",
    "DropOwnedStmt",
    "DropRoleStmt",
    "DropStmt",
    "ExecuteStmt",
    "ExplainStmt",
    "GrantRoleStmt",
    "GrantStmt",
    "ImportForeignSchemaStmt",
    "IndexStmt",
    "InsertStmt",
    "ListenStmt",
    "LoadStmt",
    "LockStmt",
    "MergeStmt",
    "NotifyStmt",
    "PrepareStmt",
    "RefreshMatViewStmt",
    "ReindexStmt",
    "RenameStmt",
    "ReplicaIdentityStmt",
    "RuleStmt",
    "SecLabelStmt",
    "TransactionStmt",
    "TruncateStmt",
    "UnlistenStmt",
    "UpdateStmt",
    "VacuumStmt",
    "VariableSetStmt",
    "ViewStmt",
}


@dataclass(frozen=True)
class QueryClassification:
    statement_type: str
    read_only: bool
    reason: str | None
    tables_referenced: list[str]


def classify_read_only_query(sql: str) -> QueryClassification:
    """Classify whether a SQL string is admissible for read-only execution."""
    if not sql or not sql.strip():
        return QueryClassification(
            statement_type="invalid",
            read_only=False,
            reason="empty_query",
            tables_referenced=[],
        )

    try:
        statements = parse_sql(sql)
    except ParseError:
        return QueryClassification(
            statement_type="invalid",
            read_only=False,
            reason="parse_error",
            tables_referenced=[],
        )

    if len(statements) != 1:
        return QueryClassification(
            statement_type="multi_statement",
            read_only=False,
            reason="multi_statement",
            tables_referenced=[],
        )

    root = statements[0].stmt
    statement_type = _statement_type(root)
    tables_referenced = _extract_table_references(root)

    if not isinstance(root, ast.SelectStmt):
        return QueryClassification(
            statement_type=statement_type,
            read_only=False,
            reason="root_statement_not_select",
            tables_referenced=tables_referenced,
        )

    if getattr(root, "intoClause", None) is not None:
        return QueryClassification(
            statement_type=statement_type,
            read_only=False,
            reason="select_into_denied",
            tables_referenced=tables_referenced,
        )

    if getattr(root, "lockingClause", None):
        return QueryClassification(
            statement_type=statement_type,
            read_only=False,
            reason="locking_clause_denied",
            tables_referenced=tables_referenced,
        )

    denied_node = _find_denied_descendant(root)
    if denied_node is not None:
        return QueryClassification(
            statement_type=statement_type,
            read_only=False,
            reason=f"{_snake_case(denied_node.__class__.__name__)}_denied",
            tables_referenced=tables_referenced,
        )

    return QueryClassification(
        statement_type=statement_type,
        read_only=True,
        reason=None,
        tables_referenced=tables_referenced,
    )


def _statement_type(node: ast.Node) -> str:
    name = node.__class__.__name__
    if name.endswith("Stmt"):
        name = name[:-4]
    return _snake_case(name)


def _snake_case(value: str) -> str:
    chars: list[str] = []
    for index, char in enumerate(value):
        if char.isupper() and index > 0 and not value[index - 1].isupper():
            chars.append("_")
        chars.append(char.lower())
    return "".join(chars)


def _find_denied_descendant(node: ast.Node) -> ast.Node | None:
    for child in _walk_nodes(node):
        if child is node:
            continue
        if child.__class__.__name__ in _DENIED_NODE_TYPES:
            return child
        if isinstance(child, ast.SelectStmt):
            if getattr(child, "intoClause", None) is not None:
                return child
            if getattr(child, "lockingClause", None):
                return child
    return None


def _extract_table_references(node: ast.Node) -> list[str]:
    cte_names = _collect_cte_names(node)
    write_targets = _collect_write_targets(node)
    seen: set[str] = set()
    tables: list[str] = []

    for child in _walk_nodes(node):
        if not isinstance(child, ast.RangeVar):
            continue
        relname = getattr(child, "relname", None)
        schemaname = getattr(child, "schemaname", None)
        catalogname = getattr(child, "catalogname", None)
        if not relname:
            continue
        if not schemaname and relname in cte_names:
            continue
        identifier = ".".join(part for part in (catalogname, schemaname, relname) if part)
        if identifier in write_targets:
            continue
        if identifier and identifier not in seen:
            seen.add(identifier)
            tables.append(identifier)

    return tables


def _collect_cte_names(node: ast.Node) -> set[str]:
    cte_names: set[str] = set()
    for child in _walk_nodes(node):
        if isinstance(child, ast.CommonTableExpr) and child.ctename:
            cte_names.add(child.ctename)
    return cte_names


def _collect_write_targets(node: ast.Node) -> set[str]:
    targets: set[str] = set()
    for child in _walk_nodes(node):
        if not isinstance(child, ast.IntoClause):
            continue
        relation = getattr(child, "rel", None)
        if not isinstance(relation, ast.RangeVar):
            continue
        relname = getattr(relation, "relname", None)
        schemaname = getattr(relation, "schemaname", None)
        catalogname = getattr(relation, "catalogname", None)
        identifier = ".".join(part for part in (catalogname, schemaname, relname) if part)
        if identifier:
            targets.add(identifier)
    return targets


def _walk_nodes(value: object) -> Iterator[ast.Node]:
    if value is None:
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            yield from _walk_nodes(item)
        return
    if not isinstance(value, ast.Node):
        return

    yield value
    for attribute in value:
        yield from _walk_nodes(getattr(value, attribute))
