import React, { useRef } from "react";
import { Animated, Pressable, StyleSheet, View } from "react-native";
import { COLORS } from "../config/theme";

export default function PressableStamp({
  children,
  style,
  stampOffset = 4,
  stampColor = COLORS.ink,
  borderRadius = 14,
  borderColor = COLORS.ink,
  borderWidth = 2,
  onPress,
  onPressIn,
  onPressOut,
  disabled,
  ...props
}) {
  const pressAnim = useRef(new Animated.Value(0)).current;

  const handlePressIn = (e) => {
    Animated.spring(pressAnim, {
      toValue: 1,
      useNativeDriver: true,
      speed: 50,
      bounciness: 4,
    }).start();
    onPressIn?.(e);
  };

  const handlePressOut = (e) => {
    Animated.spring(pressAnim, {
      toValue: 0,
      useNativeDriver: true,
      speed: 50,
      bounciness: 4,
    }).start();
    onPressOut?.(e);
  };

  const translateX = pressAnim.interpolate({
    inputRange: [0, 1],
    outputRange: [0, 2],
  });
  const translateY = pressAnim.interpolate({
    inputRange: [0, 1],
    outputRange: [0, 2],
  });
  const shadowX = pressAnim.interpolate({
    inputRange: [0, 1],
    outputRange: [stampOffset, 0],
  });
  const shadowY = pressAnim.interpolate({
    inputRange: [0, 1],
    outputRange: [stampOffset, 0],
  });
  const shadowOpacity = pressAnim.interpolate({
    inputRange: [0, 0.5, 1],
    outputRange: [1, 0.3, 0],
  });

  return (
    <View style={{ position: "relative" }}>
      <Animated.View
        style={[
          {
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            borderRadius,
            backgroundColor: stampColor,
            opacity: shadowOpacity,
            transform: [{ translateX: shadowX }, { translateY: shadowY }],
          },
        ]}
      />
      <Animated.View
        style={[
          {
            transform: [{ translateX }, { translateY }],
          },
        ]}
      >
        <Pressable
          onPress={onPress}
          onPressIn={handlePressIn}
          onPressOut={handlePressOut}
          disabled={disabled}
          style={({ pressed }) => [
            {
              backgroundColor: COLORS.card,
              borderRadius,
              borderWidth,
              borderColor,
              overflow: "hidden",
            },
            style,
          ]}
          {...props}
        >
          {children}
        </Pressable>
      </Animated.View>
    </View>
  );
}
