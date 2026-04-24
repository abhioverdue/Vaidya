/**
 * Vaidya — Image Result screen
 * Shows detailed image analysis results
 */

import { View, Text, StyleSheet, TouchableOpacity, ScrollView } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';
import Animated, { FadeInDown } from 'react-native-reanimated';
import { useTranslation } from 'react-i18next';
import { useAppStore } from '@/store';
import { COLORS, TYPE, RADIUS } from '@/constants';
import { GradientCard } from '@/components/ui/GradientCard';
import { SectionHeader } from '@/components/ui/SectionHeader';

export default function ImageResultScreen() {
  const { t } = useTranslation();
  const store = useAppStore();
  const session = store.currentSession;

  if (!session || !('vision_result' in session) || !session.vision_result) {
    return (
      <SafeAreaView style={s.safe}>
        <View style={s.center}>
          <Text style={s.errorText}>{t('image_result.no_image')}</Text>
          <TouchableOpacity onPress={() => router.back()} style={s.errorBackBtn}>
            <Text style={s.backBtnText}>{t('common.back')}</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  const vision = session.vision_result;

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
          <Text style={s.headerTitle}>{t('image_result.title')}</Text>
          <View style={{ width: 36 }} />
        </View>

        {/* Top Prediction */}
        <Animated.View entering={FadeInDown.duration(350)}>
          <GradientCard>
            <SectionHeader title={t('image_result.primary_finding')} />
            <Text style={s.primaryFinding}>{vision.top_prediction || 'Analysis complete'}</Text>
            <Text style={s.datasetType}>{t('image_result.dataset', { value: vision.dataset_type || 'Medical imaging' })}</Text>
          </GradientCard>
        </Animated.View>

        {/* All Predictions */}
        {vision.all_predictions && vision.all_predictions.length > 0 && (
          <Animated.View entering={FadeInDown.duration(350).delay(100)}>
            <GradientCard>
              <SectionHeader title={t('image_result.all_predictions')} />
              {vision.all_predictions.map((pred: any, i: number) => (
                <View key={i} style={s.predRow}>
                  <Text style={s.predLabel}>{pred.label}</Text>
                  <Text style={s.predConf}>{Math.round(pred.confidence * 100)}%</Text>
                </View>
              ))}
            </GradientCard>
          </Animated.View>
        )}

        {/* Signal Source */}
        <Animated.View entering={FadeInDown.duration(350).delay(200)}>
          <GradientCard>
            <SectionHeader title={t('image_result.method_title')} />
            <Text style={s.signalSource}>{vision.signal_source || 'Vision model'}</Text>
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
  primaryFinding: { ...TYPE.titleLarge, color: COLORS.ink, marginBottom: 8 },
  datasetType: { ...TYPE.bodySmall, color: COLORS.textMuted },
  predRow:     { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: COLORS.border },
  predLabel:   { ...TYPE.bodyMed, color: COLORS.ink, flex: 1 },
  predConf:    { ...TYPE.bodySmall, color: COLORS.sage, fontWeight: '600' },
  signalSource: { ...TYPE.bodyMed, color: COLORS.textSub },
});