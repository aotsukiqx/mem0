import { createSlice, PayloadAction } from '@reduxjs/toolkit';

export interface LLMConfig {
  model: string;
  temperature: number;
  max_tokens: number;
  api_key?: string;
  ollama_base_url?: string;
  openai_base_url?: string;
}

export interface LLMProvider {
  provider: string;
  config: LLMConfig;
}

export interface EmbedderConfig {
  model: string;
  api_key?: string;
  ollama_base_url?: string;
  openai_base_url?: string;
}

export interface EmbedderProvider {
  provider: string;
  config: EmbedderConfig;
}

export interface GraphStoreConfig {
  url: string;
  username: string;
  password: string;
}

export interface GraphStoreProvider {
  provider: string;
  config: GraphStoreConfig;
  llm?: LLMProvider;
}

export interface VectorStoreConfig {
  collection_name: string;
  url: string;
  embedding_model_dims: number;
  token?: string;
}

export interface VectorStoreProvider {
  provider: string;
  config: VectorStoreConfig;
}

export interface Mem0Config {
  llm?: LLMProvider;
  embedder?: EmbedderProvider;
  graph_store?: GraphStoreProvider;
  vector_store?: VectorStoreProvider;
  version?: string;
}

export interface OpenMemoryConfig {
  custom_instructions?: string | null;
}

export interface ConfigState {
  openmemory: OpenMemoryConfig;
  mem0: Mem0Config;
  status: 'idle' | 'loading' | 'succeeded' | 'failed';
  error: string | null;
}

const initialState: ConfigState = {
  openmemory: {
    custom_instructions: null,
  },
  mem0: {
    // 空配置，将从API加载真实的默认配置
  },
  status: 'idle',
  error: null,
};

const configSlice = createSlice({
  name: 'config',
  initialState,
  reducers: {
    setConfigLoading: (state) => {
      state.status = 'loading';
      state.error = null;
    },
    setConfigSuccess: (state, action: PayloadAction<{ openmemory?: OpenMemoryConfig; mem0: Mem0Config }>) => {
      if (action.payload.openmemory) {
        state.openmemory = action.payload.openmemory;
      }
      state.mem0 = action.payload.mem0;
      state.status = 'succeeded';
      state.error = null;
    },
    setConfigError: (state, action: PayloadAction<string>) => {
      state.status = 'failed';
      state.error = action.payload;
    },
    updateOpenMemory: (state, action: PayloadAction<OpenMemoryConfig>) => {
      state.openmemory = action.payload;
    },
    updateLLM: (state, action: PayloadAction<LLMProvider>) => {
      state.mem0.llm = action.payload;
    },
    updateEmbedder: (state, action: PayloadAction<EmbedderProvider>) => {
      state.mem0.embedder = action.payload;
    },
    updateGraphStore: (state, action: PayloadAction<GraphStoreProvider>) => {
      state.mem0.graph_store = action.payload;
    },
    updateVectorStore: (state, action: PayloadAction<VectorStoreProvider>) => {
      state.mem0.vector_store = action.payload;
    },
    updateMem0Config: (state, action: PayloadAction<Mem0Config>) => {
      state.mem0 = action.payload;
    },
  },
});

export const {
  setConfigLoading,
  setConfigSuccess,
  setConfigError,
  updateOpenMemory,
  updateLLM,
  updateEmbedder,
  updateGraphStore,
  updateVectorStore,
  updateMem0Config,
} = configSlice.actions;

export default configSlice.reducer; 