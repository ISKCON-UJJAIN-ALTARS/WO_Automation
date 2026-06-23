// src/store/useWorkOrderStore.js
import { create } from 'zustand';
import { devtools, persist } from 'zustand/middleware';
import { buildDefaultValues } from '@/utils/mergeFields';

/**
 * Central store for the whole work-order flow.
 *
 * selectedComponents: string[]            e.g. ["ceiling", "base_box"]
 * selectedTemplates:  Record<componentId, templateId>  one design choice per component
 * fieldValues:        Record<fieldKey, number>          merged, deduped values
 * generatedOrders:    GeneratedOrder[]                  history of past generations
 * currentOrder:       GeneratedOrder | null              most recent result
 */
export const useWorkOrderStore = create()(
  devtools(
    persist(
      (set, get) => ({
        selectedComponents: [],
        selectedTemplates: {},
        fieldValues: {},
        generatedOrders: [],
        currentOrder: null,
        isGenerating: false,
        generationError: null,

        toggleComponent: (componentId) =>
          set((state) => {
            const exists = state.selectedComponents.includes(componentId);
            const selectedComponents = exists
              ? state.selectedComponents.filter((c) => c !== componentId)
              : [...state.selectedComponents, componentId];

            const selectedTemplates = { ...state.selectedTemplates };
            if (exists) delete selectedTemplates[componentId];

            return { selectedComponents, selectedTemplates };
          }),

        selectTemplate: (componentId, templateId) =>
          set((state) => {
            const selectedTemplates = { ...state.selectedTemplates, [componentId]: templateId };
            const templateIds = Object.values(selectedTemplates);
            const defaults = buildDefaultValues(templateIds);
            return {
              selectedTemplates,
              fieldValues: { ...defaults, ...state.fieldValues },
            };
          }),

        setFieldValue: (key, value) =>
          set((state) => ({
            fieldValues: { ...state.fieldValues, [key]: value },
          })),

        getSelectedTemplateIds: () => Object.values(get().selectedTemplates),

        startGeneration: () => set({ isGenerating: true, generationError: null }),

        completeGeneration: (order) =>
          set((state) => ({
            isGenerating: false,
            currentOrder: order,
            generatedOrders: [order, ...state.generatedOrders],
          })),

        failGeneration: (message) => set({ isGenerating: false, generationError: message }),

        resetFlow: () =>
          set({
            selectedComponents: [],
            selectedTemplates: {},
            fieldValues: {},
            currentOrder: null,
            generationError: null,
          }),
      }),
      { name: 'divine-sky-work-order-store' }
    )
  )
);
