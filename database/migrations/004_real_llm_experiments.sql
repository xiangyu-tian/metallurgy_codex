-- M4.5: real-LLM engine, provider trace and batch linkage
ALTER TABLE metallurgy_v2.llm_tool_trace
    ADD COLUMN IF NOT EXISTS experiment_engine VARCHAR(32) NOT NULL DEFAULT 'deterministic',
    ADD COLUMN IF NOT EXISTS tool_call_chain JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS llm_trace JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE metallurgy_v2.experiment_run
    ADD COLUMN IF NOT EXISTS benchmark_run_id VARCHAR(64);

CREATE INDEX IF NOT EXISTS idx_experiment_benchmark_run
    ON metallurgy_v2.experiment_run(benchmark_run_id);

COMMENT ON COLUMN metallurgy_v2.llm_tool_trace.experiment_engine
    IS 'Experiment engine, for example deterministic or deepseek';
COMMENT ON COLUMN metallurgy_v2.llm_tool_trace.tool_call_chain
    IS 'Ordered function calls with generated arguments, validation and execution';
COMMENT ON COLUMN metallurgy_v2.llm_tool_trace.llm_trace
    IS 'Sanitized provider requests and responses without credentials';
COMMENT ON COLUMN metallurgy_v2.experiment_run.benchmark_run_id
    IS 'Groups all case experiments produced by one benchmark batch';
