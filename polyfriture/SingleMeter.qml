import QtQuick 2.15
import "iec.js" as IECFunctions

Rectangle {
    id: meter
    anchors.fill: parent
    color: "black"
    clip: true
    required property real levelMax
    required property real levelRms
    required property real levelIECMaxBallistic
    function fraction(value) { return Math.max(0, Math.min(1, value)); }
    function peakColor(value) {
        if (value > .8) return "#F00014";
        if (value > .7) return "#F0A014";
        if (value > .6) return "#DCDC14";
        if (value > .4) return "#A0DC14";
        if (value > .2) return "#28A028";
        return "#20B020";
    }

    Gradient {
        id: maxGradient
        GradientStop { position: 0.2; color: "#F00014" }
        GradientStop { position: 0.3; color: "#F0A014" }
        GradientStop { position: 0.4; color: "#DCDC14" }
        GradientStop { position: 0.6; color: "#A0DC14" }
        GradientStop { position: 0.8; color: "#28A028" }
    }
    Gradient {
        id: rmsGradient
        GradientStop { position: 0.0; color: "#E6E6FF" }
        GradientStop { position: 0.7; color: "#0000FF" }
        GradientStop { position: 1.0; color: "#000096" }
    }
    Item {
        width: parent.width
        height: meter.fraction(IECFunctions.dB_to_IEC(meter.levelMax)) * parent.height
        anchors.bottom: parent.bottom
        clip: true
        Rectangle {
            width: parent.width
            height: meter.height
            anchors.bottom: parent.bottom
            gradient: maxGradient
        }
    }
    Item {
        width: parent.width
        height: meter.fraction(IECFunctions.dB_to_IEC(meter.levelRms)) * parent.height
        anchors.bottom: parent.bottom
        clip: true
        Rectangle {
            width: parent.width
            height: meter.height
            anchors.bottom: parent.bottom
            gradient: rmsGradient
        }
    }
    Rectangle {
        width: parent.width
        height: 1
        y: Math.min(meter.height - 1, (1 - meter.fraction(meter.levelIECMaxBallistic)) * meter.height)
        color: meter.peakColor(meter.levelIECMaxBallistic)
    }
}
