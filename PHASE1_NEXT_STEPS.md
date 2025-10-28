# Phase 1 Implementation: Next Steps

## Current Status

✅ **Completed**:
- Week 1-4: All implementations validated and working
- CI/CD: All checks passing
- Observability: Metrics, tracing, dashboard complete
- Performance: Caching (410x), rate limiting operational
- Documentation: Comprehensive validation and debugging docs

## Phase 1: Standardization (Ready to Implement)

### 1. JSON Schema Export (Highest Priority)

**Why**: Makes NBA MCP easy to use with any LLM (GPT, Claude, Gemini)

**Implementation Steps**:

1. **Create schema publisher** (`nba_mcp/schemas/publisher.py`):
   ```python
   def export_all_schemas():
       """Export all tool parameter schemas."""
       tools = {
           "resolve_entity": {...},
           "get_league_leaders": LeagueLeadersParams.model_json_schema(),
           # ... all 20+ tools
       }

       # Write to schemas/*.json
       for name, schema in tools.items():
           Path(f"schemas/{name}.json").write_text(
               json.dumps(schema, indent=2)
           )
   ```

2. **Generate OpenAPI spec** (`schemas/openapi.yaml`):
   - All tools as REST endpoints (for compatibility)
   - Request/response schemas
   - Examples and descriptions

3. **Add schema validation**:
   - Validate all tool calls match schema
   - Catch parameter errors early
   - Better error messages

**Benefits**:
- LLMs auto-discover available tools
- Stable API contracts
- Better documentation
- OpenAPI/Swagger compatibility

### 2. User-Agent Headers (Quick Win)

**Why**: Be a good API citizen, reduce rate limiting risk

**Implementation**:
```python
# nba_mcp/api/client.py
HEADERS = {
    "User-Agent": "NBA-MCP/1.0.0 (https://github.com/your-org/nba_mcp)",
    "Referer": "https://stats.nba.com",
    "Accept": "application/json"
}

class NBAApiClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
```

**Time**: 30 minutes
**Risk**: Very low
**Impact**: Reduced IP bans, better rate limits

### 3. Schema Drift Detection (Reliability)

**Why**: NBA API changes schema without notice, we need to detect and handle

**Implementation**:
```python
# nba_mcp/api/schema_validator.py
class SchemaValidator:
    def validate(self, endpoint, response):
        """Validate response matches expected schema."""
        expected = self.schemas[endpoint]

        # Check required fields
        missing = set(expected["required"]) - set(response.keys())
        if missing:
            raise UpstreamSchemaError(missing_fields=missing)

        # Check types
        for field, expected_type in expected["types"].items():
            if field in response:
                actual = type(response[field]).__name__
                if actual != expected_type:
                    warnings.warn(f"Type mismatch: {field}")
```

**Benefits**:
- Early detection of API changes
- Graceful degradation
- Automatic alerts

### 4. Versioning Support

**Why**: Allow v1 and v2 to coexist during breaking changes

**Implementation**:
- Add `schema_version` to ResponseMetadata
- Use explicit version in tool names (`get_player_stats_v1`)
- Default tool name always points to latest version

## Recommended Implementation Order

### Week 5 (Standardization)
**Day 1-2**: JSON Schema Export
- Create `nba_mcp/schemas/publisher.py`
- Export all tool schemas to `schemas/*.json`
- Test with OpenAPI validator

**Day 2-3**: User-Agent + Schema Validation
- Add headers to NBA API client
- Create `SchemaValidator` class
- Add validation to key endpoints

**Day 3-4**: Versioning
- Add `schema_version` to metadata
- Create versioned tool variants
- Document migration path

**Day 4-5**: Testing & Documentation
- Run full validation suite
- Update README with schema docs
- Add examples for each tool

## Quick Start Commands

```bash
# Export all schemas
python -c "from nba_mcp.schemas import export_all_schemas; export_all_schemas()"

# Validate a schema
python -c "from nba_mcp.schemas import get_tool_schema; print(get_tool_schema('get_player_stats'))"

# Run validation with real API (limited)
pytest tests/test_golden_queries.py --real-api --limit=5

# Check CI status
git push && echo "Check GitHub Actions"
```

## Success Metrics

After Phase 1 completion:
- [ ] 20+ JSON Schema files in `schemas/` directory
- [ ] OpenAPI spec generated and validated
- [ ] User-Agent headers in all API calls
- [ ] Schema drift detection on 10+ key endpoints
- [ ] Versioning system documented and tested
- [ ] All CI checks passing
- [ ] Documentation updated

## Files to Create

### New Files
1. `nba_mcp/schemas/__init__.py` ✅ Created
2. `nba_mcp/schemas/publisher.py` (TODO)
3. `nba_mcp/api/schema_validator.py` (TODO)
4. `schemas/*.json` (20+ files, generated)
5. `schemas/openapi.yaml` (generated)
6. `tests/test_schema_export.py` (TODO)

### Modified Files
1. `nba_mcp/api/client.py` (add headers)
2. `nba_mcp/api/models.py` (add schema_version)
3. `nba_mcp/nba_server.py` (integrate schema validation)
4. `README.md` (add schema docs)

## Risks & Mitigation

### Risk 1: NBA API Changes During Implementation
**Mitigation**: Schema validation will catch this immediately

### Risk 2: Performance Impact of Validation
**Mitigation**: Only validate in development, skip in production with flag

### Risk 3: Breaking Changes to Existing Users
**Mitigation**: Versioning ensures backward compatibility

## Next Session Checklist

When resuming work:
1. Review `STANDARDIZATION_PLAN.md`
2. Review `PHASE1_NEXT_STEPS.md` (this file)
3. Check CI status on GitHub
4. Run `python run_validation.py` to ensure still working
5. Start with JSON Schema export (highest value)

## Questions to Consider

1. **Schema Storage**: File-based (current plan) vs database?
   - **Recommendation**: File-based for simplicity, commit to git

2. **Schema Updates**: Manual vs automatic?
   - **Recommendation**: Automatic export on tool changes (git pre-commit hook)

3. **Validation Level**: Development-only vs production?
   - **Recommendation**: Development + staging, optional in production

4. **LLM Integration**: Which LLMs to test with?
   - **Recommendation**: GPT-4, Claude 3.5, Gemini Pro

## Resources

- **JSON Schema Docs**: https://json-schema.org/
- **OpenAPI Spec**: https://swagger.io/specification/
- **Pydantic JSON Schema**: https://docs.pydantic.dev/latest/concepts/json_schema/
- **MCP Protocol**: https://modelcontextprotocol.io/

## Summary

Phase 1 focuses on **standardization** to make NBA MCP:
- ✅ Easy to discover (JSON Schemas)
- ✅ Easy to use (any LLM)
- ✅ Reliable (schema validation)
- ✅ Professional (versioning, headers)

**Estimated Time**: 4-5 days
**Complexity**: Medium
**Value**: Very High (enables wider adoption)

---

**Status**: Ready to implement
**Priority**: High
**Dependencies**: None (builds on existing work)
