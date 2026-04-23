/**
 * Vaidya — Fusion Detail screen
 * Explains how multimodal signals were fused
 */

import { View, Text, StyleSheet, TouchableOpacity, ScrollView } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import Animated, { FadeInDown } from 'react-native-reanimated';
import { useAppStore } from '@/store';
import { COLORS, TYPE, RADIUS } from '@/constants';
import { GradientCard } from '@/components/ui/GradientCard';
import { SectionHeader } from '@/components/ui/SectionHeader';

export default function FusionDetailScreen() {
  const store = useAppStore();
  const session = store.currentSession;

  if (!session || !('fusion_weights' in session) || !session.fusion_weights) {
    return (
      <SafeAreaView style={s.safe}>
        <View style={s.center}>
          <Text style={s.errorText}>No fusion details available</Text>
          <TouchableOpacity onPress={() => router.back()} style={s.errorBackBtn}>
            <Text style={s.backBtnText}>Go Back</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  const weights = session.fusion_weights;
  const hasAudio = 'audio_result' in session && session.audio_result;
  const hasVision = 'vision_result' in session && session.vision_result;

  return (
    <SafeAreaView style={s.safe}>
      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>
        {/* Header */}
        <View style={s.header}>
          <TouchableOpacity onPress={() => router.back()} style={s.backBtn}>
            <View style={s.backCircle}>
              <Text style={s.backGlyph}>←</Text>
            </View>
          </TouchableOpacity>
          <Text style={s.headerTitle}>Diagnosis Fusion</Text>
          <View style={{ width: 36 }} />
        </View>

        {/* Explanation */}
        <Animated.View entering={FadeInDown.duration(350)}>
          <GradientCard>
            <SectionHeader title="How It Works" />
            <Text style={s.explanation}>
              Vaidya combines multiple AI models for accurate diagnosis. Each modality (text, audio, image)
              provides independent signals that are weighted and fused using confidence-based voting.
            </Text>
          </GradientCard>
        </Animated.View>

        {/* Fusion Weights */}
        <Animated.View entering={FadeInDown.duration(350).delay(100)}>
          <GradientCard>
            <SectionHeader title="Signal Weights" />
            <View style={s.weightsContainer}>
              <View style={s.weightRow}>
                <Text style={s.weightLabel}>Text Analysis (XGBoost)</Text>
                <Text style={s.weightValue}>{Math.round(weights.nlp * 100)}%</Text>
              </View>
              {hasAudio && (
                <View style={s.weightRow}>
                  <Text style={s.weightLabel}>Audio Analysis</Text>
                  <Text style={s.weightValue}>{Math.round(weights.audio * 100)}%</Text>
                </View>
              )}
              {hasVision && (
                <View style={s.weightRow}>
                  <Text style={s.weightLabel}>Image Analysis</Text>
                  <Text style={s.weightValue}>{Math.round(weights.vision * 100)}%</Text>
                </View>
              )}
            </View>
          </GradientCard>
        </Animated.View>

        {/* Modalities Used */}
        <Animated.View entering={FadeInDown.duration(350).delay(200)}>
          <GradientCard>
            <SectionHeader title="Modalities Analyzed" />
            <View style={s.modalities}>
              <View style={s.modalityItem}>
                <Text style={s.modalityIcon}>📝</Text>
                <Text style={s.modalityText}>Text symptoms</Text>
              </View>
              {hasAudio && (
                <View style={s.modalityItem}>
                  <Text style={s.modalityIcon}>🎤</Text>
                  <Text style={s.modalityText}>Respiratory audio</Text>
                </View>
              )}
              {hasVision && (
                <View style={s.modalityItem}>
                  <Text style={s.modalityIcon}>📷</Text>
                  <Text style={s.modalityText}>Medical image</Text>
                </View>
              )}
            </View>
          </GradientCard>
        </Animated.View>

        {/* Final Diagnosis */}
        <Animated.View entering={FadeInDown.duration(350).delay(300)}>
          <GradientCard>
            <SectionHeader title="Final Diagnosis" />
            <Text style={s.finalDiagnosis}>{session.diagnosis.primary_diagnosis}</Text>
            <Text style={s.diagnosisSource}>Source: {session.diagnosis.diagnosis_source}</Text>
          </GradientCard>
        </Animated.View>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe:          { flex: 1, backgroundColor: COLORS.parchment },
  center:        { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 20 },
  errorText:     { ...TYPE.titleMed, color: COLORS.textMuted, textAlign: 'center', marginBottom: 20 },
  errorBackBtn:  { backgroundColor: COLORS.ink, borderRadius: RADIUS.lg, paddingVertical: 12, paddingHorizontal: 24 },
  backBtnText:   { ...TYPE.titleMed, color: '#fff' },
  scroll:        { paddingHorizontal: 20, paddingTop: 20, paddingBottom: 24 },
  header:        { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 14, marginBottom: 20 },
  backBtn:     { width: 40 },
  backCircle:  { width: 36, height: 36, borderRadius: 18, backgroundColor: COLORS.surface, borderWidth: 1, borderColor: COLORS.border, alignItems: 'center', justifyContent: 'center' },
  backGlyph:   { fontSize: 18, color: COLORS.ink, marginTop: -1 },
  headerTitle: { ...TYPE.titleLarge, color: COLORS.ink },
  explanation: { ...TYPE.bodyMed, color: COLORS.textSub, lineHeight: 22 },
  weightsContainer: { gap: 12 },
  weightRow:   { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 8 },
  weightLabel: { ...TYPE.bodyMed, color: COLORS.ink, flex: 1 },
  weightValue: { ...TYPE.bodySmall, color: COLORS.sage, fontWeight: '600' },
  modalities:  { flexDirection: 'row', flexWrap: 'wrap', gap: 16 },
  modalityItem:{ alignItems: 'center', gap: 8, flex: 1, minWidth: 80 },
  modalityIcon:{ fontSize: 24 },
  modalityText:{ ...TYPE.bodySmall, color: COLORS.textMuted, textAlign: 'center' },
  finalDiagnosis: { ...TYPE.titleMed, color: COLORS.ink, marginBottom: 8 },
  diagnosisSource: { ...TYPE.bodySmall, color: COLORS.textFaint },
});