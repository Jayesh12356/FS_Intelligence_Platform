import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FadeIn, PageMotion, StaggerItem, StaggerList } from "./MotionWrap";

describe("MotionWrap helpers", () => {
  it("PageMotion renders children inside a div", () => {
    render(
      <PageMotion>
        <span>content</span>
      </PageMotion>,
    );
    expect(screen.getByText("content")).toBeInTheDocument();
  });

  it("FadeIn accepts a delay and still renders children", () => {
    render(
      <FadeIn delay={0.1}>
        <p>visible</p>
      </FadeIn>,
    );
    expect(screen.getByText("visible")).toBeInTheDocument();
  });

  it("StaggerList + StaggerItem render nested children", () => {
    render(
      <StaggerList>
        <StaggerItem>
          <span>one</span>
        </StaggerItem>
        <StaggerItem>
          <span>two</span>
        </StaggerItem>
      </StaggerList>,
    );
    expect(screen.getByText("one")).toBeInTheDocument();
    expect(screen.getByText("two")).toBeInTheDocument();
  });
});
