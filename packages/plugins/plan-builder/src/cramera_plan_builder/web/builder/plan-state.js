/**
 * The plan being composed: its robots and their steps, its objects, and which robot is
 * edited; the plan document is kept in the protocol's JSON form, so it is what is saved,
 * generated and run.
 */

import {
  ObjectModelKey,
  PlacementMode,
  PlanBuilderCatalogKey,
  PlanBuilderLimitsKey,
  PlanKey,
  PlannedObjectKey,
  PlannedRobotKey,
  PlanStepKey,
  RobotModelKey,
  StepConstraintKey,
  StepKind,
} from '../../../protocol.js';
import { PlanPose } from './poses.js';

/**
 * The name of a new plan.
 */
export const NEW_PLAN_NAME = 'new_plan';

/**
 * The prefixes of the identities the builder gives robots and steps.
 */
export const IdentityPrefix = Object.freeze({ ROBOT: 'robot_', STEP: 'step_', OBJECT: 'object_' });

/**
 * What an object identity may hold; other characters of a model's name become `_`.
 */
const NON_IDENTITY_CHARACTERS = /[^A-Za-z0-9_]+/g;

/**
 * What an object identity must start with.
 */
const IDENTITY_START = /^[A-Za-z]/;

/**
 * Where new robots stand, in metres: the first at the origin, the next beside it.
 */
const ROBOT_SPACING = 1.5;

/**
 * Where the builder puts what it adds relative to the robot, in metres.
 */
const Placement = Object.freeze({
  NAVIGATION_AHEAD: 1.0,
  NEXT_NAVIGATION_STEP: 0.4,
  OBJECT_AHEAD: 0.7,
  OBJECT_HEIGHT: 0.8,
  OBJECT_SPREAD: 0.15,
  PUT_DOWN_BESIDE: 0.3,
});

/**
 * The step kinds that act on an object.
 */
export const OBJECT_STEPS = Object.freeze([StepKind.TRANSPORT, StepKind.PICK_UP, StepKind.PLACE]);

/**
 * The step kinds that put an object down, at a pose or on a surface.
 */
export const PUTTING_DOWN = Object.freeze([StepKind.TRANSPORT, StepKind.PLACE]);

/**
 * The step kinds that use an arm.
 */
const ARM_STEPS = Object.freeze([StepKind.PARK_ARMS, ...OBJECT_STEPS]);

// %% errors

/**
 * A change the catalog or the limits do not allow.
 */
export class PlanRefused extends Error {}

// %% state

export class PlanState {
  /**
   * The catalog the plan is composed from.
   * @type {Object}
   */
  #catalog;

  /**
   * The plan document.
   * @type {Object}
   */
  #plan;

  /**
   * The identity of the robot whose steps are edited.
   * @type {string|null}
   */
  #activeRobot;

  /**
   * @param {Object} catalog The plan builder's catalog.
   * @param {Object} plan A plan document.
   */
  constructor(catalog, plan) {
    this.#catalog = catalog;
    this.#plan = structuredClone(plan);
    this.#plan[PlanKey.ROBOTS] ??= [];
    this.#plan[PlanKey.OBJECTS] ??= [];
    for (const robot of this.#plan[PlanKey.ROBOTS]) robot[PlannedRobotKey.STEPS] ??= [];
    this.#activeRobot = plan[PlanKey.SELECTED_ROBOT] ?? this.robots()[0]?.[PlannedRobotKey.IDENTIFIER] ?? null;
  }

  /**
   * @param {Object} catalog The plan builder's catalog.
   * @param {string|null} environment The environment bundle, or null for an empty floor.
   * @param {string|null=} preferred The robot model to start with when the catalog has
   *   it.
   * @returns {PlanState} A new plan with one robot: of the preferred model, else of the
   *   model offering the most steps.
   */
  static empty(catalog, environment, preferred = null) {
    const plan = { [PlanKey.NAME]: NEW_PLAN_NAME };
    if (environment) plan[PlanKey.ENVIRONMENT] = environment;
    const state = new PlanState(catalog, plan);
    const models = [...catalog[PlanBuilderCatalogKey.ROBOTS]];
    models.sort((first, second) => second[RobotModelKey.STEPS].length - first[RobotModelKey.STEPS].length);
    const chosen = models.find((model) => model[RobotModelKey.NAME] === preferred) ?? models[0];
    if (chosen) state.addRobot(chosen[RobotModelKey.NAME]);
    return state;
  }

  /**
   * @returns {Object} The catalog the plan is composed from.
   */
  get catalog() {
    return this.#catalog;
  }

  /**
   * @returns {Object} A copy of the plan document, naming the edited robot as the one
   *   that performs.
   */
  get document() {
    const plan = structuredClone(this.#plan);
    if (this.#activeRobot !== null) plan[PlanKey.SELECTED_ROBOT] = this.#activeRobot;
    return plan;
  }

  /**
   * @returns {Object} The limits plans stay within.
   */
  get limits() {
    return this.#catalog[PlanBuilderCatalogKey.LIMITS] ?? {};
  }

  // %% plan

  /**
   * @param {string} key A `PlanKey` value: the name, the task or the environment.
   * @param {string|null} value Its new value; null or empty leaves it out.
   */
  setField(key, value) {
    if (value === null || value === '') delete this.#plan[key];
    else this.#plan[key] = value;
  }

  /**
   * @param {string} key A `PlanKey` value.
   * @returns {string} Its value, or the empty text.
   */
  field(key) {
    return this.#plan[key] ?? '';
  }

  // %% robots

  /**
   * @returns {Array<Object>} The robots, in the order they were added.
   */
  robots() {
    return this.#plan[PlanKey.ROBOTS];
  }

  /**
   * @param {string} identifier A robot's identity.
   * @returns {Object} The robot.
   * @throws {PlanRefused} When the plan has no such robot.
   */
  robot(identifier) {
    const robot = this.robots().find((candidate) => candidate[PlannedRobotKey.IDENTIFIER] === identifier);
    if (!robot) throw new PlanRefused(`The plan has no robot ${identifier}.`);
    return robot;
  }

  /**
   * @returns {Object|null} The robot whose steps are edited.
   */
  activeRobot() {
    return this.#activeRobot === null ? null : this.robot(this.#activeRobot);
  }

  /**
   * @param {string} identifier The robot whose steps to edit.
   */
  selectRobot(identifier) {
    this.robot(identifier);
    this.#activeRobot = identifier;
  }

  /**
   * @param {string} name The class name of a robot model.
   * @returns {Object} The model as the catalog lists it.
   * @throws {PlanRefused} When the catalog has no such model.
   */
  model(name) {
    const model = this.#catalog[PlanBuilderCatalogKey.ROBOTS].find((candidate) => candidate[RobotModelKey.NAME] === name);
    if (!model) throw new PlanRefused(`The catalog has no robot ${name}.`);
    return model;
  }

  /**
   * @param {Object} robot A robot of the plan.
   * @returns {Array<string>} The `StepKind` values its model offers.
   */
  offeredSteps(robot) {
    return this.model(robot[PlannedRobotKey.MODEL])[RobotModelKey.STEPS];
  }

  /**
   * @param {Object} robot A robot of the plan.
   * @returns {Array<string>} The arm choices its model offers; the choice naming every
   *   arm comes last.
   */
  offeredArms(robot) {
    return this.model(robot[PlannedRobotKey.MODEL])[RobotModelKey.ARMS];
  }

  /**
   * @param {string} modelName The class name of a robot model.
   * @returns {string} The new robot's identity; it is edited from now on.
   * @throws {PlanRefused} When the plan holds as many robots as it may.
   */
  addRobot(modelName) {
    this.model(modelName);
    this.#within(this.robots(), PlanBuilderLimitsKey.MAXIMUM_ROBOTS);
    const identifier = this.#nextIdentity(IdentityPrefix.ROBOT, this.robots().map((robot) => robot[PlannedRobotKey.IDENTIFIER]));
    const sameModel = this.robots().filter((robot) => robot[PlannedRobotKey.MODEL] === modelName).length;
    this.robots().push({
      [PlannedRobotKey.IDENTIFIER]: identifier,
      [PlannedRobotKey.MODEL]: modelName,
      [PlannedRobotKey.LABEL]: `${modelName} ${sameModel + 1}`,
      [PlannedRobotKey.POSE]: PlanPose.of(0, this.robots().length * ROBOT_SPACING, 0, 0),
      [PlannedRobotKey.JOINT_POSITIONS]: {},
      [PlannedRobotKey.STEPS]: [],
    });
    this.#activeRobot = identifier;
    return identifier;
  }

  /**
   * Remove a robot; the plan keeps at least one.
   * @param {string} identifier The robot's identity.
   * @returns {boolean} Whether it was removed.
   */
  removeRobot(identifier) {
    if (this.robots().length <= 1) return false;
    this.robot(identifier);
    this.#plan[PlanKey.ROBOTS] = this.robots().filter((robot) => robot[PlannedRobotKey.IDENTIFIER] !== identifier);
    if (this.#activeRobot === identifier) this.#activeRobot = this.robots()[0][PlannedRobotKey.IDENTIFIER];
    return true;
  }

  /**
   * Change a robot's model, keeping the steps the new model offers with arms it has;
   * its posture belongs to the old model and is dropped, and a name made from the old
   * model's name takes the new one's.
   * @param {string} identifier The robot's identity.
   * @param {string} modelName The class name of the new model.
   * @returns {number} How many steps were dropped.
   */
  setRobotModel(identifier, modelName) {
    const robot = this.robot(identifier);
    this.model(modelName);
    const previous = robot[PlannedRobotKey.MODEL];
    if (robot[PlannedRobotKey.LABEL].startsWith(`${previous} `)) robot[PlannedRobotKey.LABEL] = `${modelName}${robot[PlannedRobotKey.LABEL].slice(previous.length)}`;
    robot[PlannedRobotKey.MODEL] = modelName;
    robot[PlannedRobotKey.JOINT_POSITIONS] = {};
    const offered = this.offeredSteps(robot);
    const arms = this.offeredArms(robot);
    const kept = robot[PlannedRobotKey.STEPS].filter((step) => offered.includes(step[PlanStepKey.KIND]));
    for (const step of kept) {
      if (step[PlanStepKey.ARM] !== undefined && !arms.includes(step[PlanStepKey.ARM])) step[PlanStepKey.ARM] = this.#defaultArm(robot, step[PlanStepKey.KIND]);
    }
    const dropped = robot[PlannedRobotKey.STEPS].length - kept.length;
    robot[PlannedRobotKey.STEPS] = kept;
    return dropped;
  }

  /**
   * @param {string} identifier The robot's identity.
   * @param {string} label Its new display name; a blank one keeps the old.
   */
  setRobotLabel(identifier, label) {
    if (label.trim()) this.robot(identifier)[PlannedRobotKey.LABEL] = label.trim();
  }

  /**
   * @param {string} identifier The robot's identity.
   * @param {Array<number>} pose Where it starts.
   */
  setRobotPose(identifier, pose) {
    this.robot(identifier)[PlannedRobotKey.POSE] = pose;
  }

  /**
   * @param {string} identifier The robot's identity.
   * @param {Object<string, number>} positions Its start posture by joint name.
   */
  setRobotPosture(identifier, positions) {
    this.robot(identifier)[PlannedRobotKey.JOINT_POSITIONS] = { ...positions };
  }

  // %% steps

  /**
   * @returns {Array<Object>} The edited robot's steps, in the order they run.
   */
  steps() {
    return this.activeRobot()?.[PlannedRobotKey.STEPS] ?? [];
  }

  /**
   * @param {string} identifier A step of the edited robot.
   * @returns {Object} The step.
   * @throws {PlanRefused} When the robot has no such step.
   */
  step(identifier) {
    const step = this.steps().find((candidate) => candidate[PlanStepKey.IDENTIFIER] === identifier);
    if (!step) throw new PlanRefused(`The robot has no step ${identifier}.`);
    return step;
  }

  /**
   * Add a step to the edited robot with parameters it can run with right away.
   * @param {string} kind A `StepKind` value the robot's model offers.
   * @param {number=} index Where the step goes; at the end by default.
   * @returns {string} The step's identity.
   * @throws {PlanRefused} When the model does not offer the kind or the plan is full.
   */
  addStep(kind, index = this.steps().length) {
    const robot = this.activeRobot();
    if (!robot || !this.offeredSteps(robot).includes(kind)) throw new PlanRefused(`The robot cannot ${kind}.`);
    this.#within(this.steps(), PlanBuilderLimitsKey.MAXIMUM_STEPS);
    const identifier = this.#nextIdentity(IdentityPrefix.STEP, this.steps().map((step) => step[PlanStepKey.IDENTIFIER]));
    const step = { [PlanStepKey.IDENTIFIER]: identifier, [PlanStepKey.KIND]: kind, [PlanStepKey.CONSTRAINTS]: [] };
    if (ARM_STEPS.includes(kind)) step[PlanStepKey.ARM] = this.#defaultArm(robot, kind);
    if (kind === StepKind.MOVE_TORSO) step[PlanStepKey.TORSO_STATE] = this.#catalog[PlanBuilderCatalogKey.TORSO_STATES][0];
    if (kind === StepKind.NAVIGATE) step[PlanStepKey.TARGET] = this.#nextNavigationTarget(robot);
    if (OBJECT_STEPS.includes(kind) && this.objects().length > 0) step[PlanStepKey.OBJECT] = this.objects()[0][PlannedObjectKey.IDENTIFIER];
    if (PUTTING_DOWN.includes(kind)) this.#putDownBeside(step);
    this.steps().splice(index, 0, step);
    return identifier;
  }

  /**
   * @param {string} identifier A step of the edited robot.
   */
  removeStep(identifier) {
    this.step(identifier);
    const robot = this.activeRobot();
    robot[PlannedRobotKey.STEPS] = this.steps().filter((step) => step[PlanStepKey.IDENTIFIER] !== identifier);
  }

  /**
   * @param {string} identifier A step of the edited robot.
   * @param {number} offset How many places it moves, negative for earlier.
   */
  moveStep(identifier, offset) {
    const steps = this.steps();
    const from = steps.indexOf(this.step(identifier));
    const to = from + offset;
    if (to < 0 || to >= steps.length) return;
    const [step] = steps.splice(from, 1);
    steps.splice(to, 0, step);
  }

  /**
   * @param {string} identifier A step of the edited robot.
   * @param {Object} changes Parameters by their `PlanStepKey`; null removes one.
   */
  updateStep(identifier, changes) {
    const step = this.step(identifier);
    for (const [key, value] of Object.entries(changes)) {
      if (value === null) delete step[key];
      else step[key] = value;
    }
    if (changes[PlanStepKey.PLACEMENT] === PlacementMode.POSE && step[PlanStepKey.TARGET] === undefined) this.#putDownBeside(step);
    if (changes[PlanStepKey.PLACEMENT] === PlacementMode.SURFACE) step[PlanStepKey.SURFACE_TYPE] ??= this.#catalog[PlanBuilderCatalogKey.SURFACE_TYPES][0];
  }

  /**
   * @param {string} identifier A step of the edited robot.
   * @param {Object} constraint A compiled `StepConstraint`.
   * @returns {boolean} Whether it was attached; a step holds each sentence once.
   * @throws {PlanRefused} When the step holds as many constraints as it may.
   */
  attachConstraint(identifier, constraint) {
    const constraints = this.step(identifier)[PlanStepKey.CONSTRAINTS];
    if (constraints.some((attached) => attached[StepConstraintKey.TEXT] === constraint[StepConstraintKey.TEXT])) return false;
    this.#within(constraints, PlanBuilderLimitsKey.MAXIMUM_CONSTRAINTS);
    constraints.push(constraint);
    return true;
  }

  /**
   * @param {string} identifier A step of the edited robot.
   * @param {number} index The position of the constraint to remove.
   */
  detachConstraint(identifier, index) {
    this.step(identifier)[PlanStepKey.CONSTRAINTS].splice(index, 1);
  }

  // %% objects

  /**
   * @returns {Array<Object>} The free objects, in the order they were added.
   */
  objects() {
    return this.#plan[PlanKey.OBJECTS];
  }

  /**
   * @param {string} identifier An object's identity.
   * @returns {Object} The object.
   * @throws {PlanRefused} When the plan has no such object.
   */
  object(identifier) {
    const found = this.objects().find((candidate) => candidate[PlannedObjectKey.IDENTIFIER] === identifier);
    if (!found) throw new PlanRefused(`The plan has no object ${identifier}.`);
    return found;
  }

  /**
   * Add a copy of an object model in front of the edited robot, spread out from the
   * objects added before.
   * @param {string} modelIdentifier The identifier of an object model.
   * @returns {string} The object's identity, made from the model's name.
   * @throws {PlanRefused} When the catalog has no such model or the plan is full.
   */
  addObject(modelIdentifier) {
    const model = this.#catalog[PlanBuilderCatalogKey.OBJECTS].find((candidate) => candidate[ObjectModelKey.IDENTIFIER] === modelIdentifier);
    if (!model) throw new PlanRefused(`The catalog has no object ${modelIdentifier}.`);
    this.#within(this.objects(), PlanBuilderLimitsKey.MAXIMUM_OBJECTS);
    const base = model[ObjectModelKey.NAME].replace(NON_IDENTITY_CHARACTERS, '_');
    const name = IDENTITY_START.test(base) ? base : `${IdentityPrefix.OBJECT}${base}`;
    const taken = this.objects().map((item) => item[PlannedObjectKey.IDENTIFIER]);
    const identifier = taken.includes(name) ? this.#nextIdentity(`${name}_`, taken) : name;
    const robotPose = this.activeRobot()?.[PlannedRobotKey.POSE] ?? PlanPose.of(0, 0, 0, 0);
    const [x, y] = PlanPose.position(robotPose);
    const yaw = PlanPose.yaw(robotPose);
    const sideways = (this.objects().length % 2 === 0 ? 1 : -1) * Math.ceil(this.objects().length / 2) * Placement.OBJECT_SPREAD;
    this.objects().push({
      [PlannedObjectKey.IDENTIFIER]: identifier,
      [PlannedObjectKey.MODEL]: modelIdentifier,
      [PlannedObjectKey.POSE]: PlanPose.of(
        PlanPose.rounded(x + Placement.OBJECT_AHEAD * Math.cos(yaw) - sideways * Math.sin(yaw)),
        PlanPose.rounded(y + Placement.OBJECT_AHEAD * Math.sin(yaw) + sideways * Math.cos(yaw)),
        Placement.OBJECT_HEIGHT,
        0,
      ),
    });
    return identifier;
  }

  /**
   * Remove an object; steps acting on it act on the first remaining object, or on none.
   * @param {string} identifier The object's identity.
   */
  removeObject(identifier) {
    this.object(identifier);
    this.#plan[PlanKey.OBJECTS] = this.objects().filter((item) => item[PlannedObjectKey.IDENTIFIER] !== identifier);
    const replacement = this.objects()[0]?.[PlannedObjectKey.IDENTIFIER];
    for (const robot of this.robots()) {
      for (const step of robot[PlannedRobotKey.STEPS]) {
        if (step[PlanStepKey.OBJECT] !== identifier) continue;
        if (replacement === undefined) delete step[PlanStepKey.OBJECT];
        else step[PlanStepKey.OBJECT] = replacement;
      }
    }
  }

  /**
   * @param {string} identifier The object's identity.
   * @param {Array<number>} pose Where it starts.
   */
  setObjectPose(identifier, pose) {
    this.object(identifier)[PlannedObjectKey.POSE] = pose;
  }

  /**
   * @param {string} identifier The object's identity.
   * @param {string|null} color A CSS hexadecimal colour, or null for the model's own.
   */
  setObjectColor(identifier, color) {
    const found = this.object(identifier);
    if (color === null) delete found[PlannedObjectKey.COLOR];
    else found[PlannedObjectKey.COLOR] = color;
  }

  // %% defaults

  /**
   * @param {Object} robot A robot of the plan.
   * @param {string} kind A `StepKind` value using an arm.
   * @returns {string} Parking uses every arm, other steps the first choice.
   */
  #defaultArm(robot, kind) {
    const arms = this.offeredArms(robot);
    return kind === StepKind.PARK_ARMS ? arms[arms.length - 1] : arms[0];
  }

  /**
   * @param {Object} robot A robot of the plan.
   * @returns {Array<number>} A little beyond its last navigation target, or ahead of it.
   */
  #nextNavigationTarget(robot) {
    const previous = robot[PlannedRobotKey.STEPS].filter((step) => step[PlanStepKey.KIND] === StepKind.NAVIGATE).pop();
    if (previous) {
      const [x, y, z] = PlanPose.position(previous[PlanStepKey.TARGET]);
      return PlanPose.moved(previous[PlanStepKey.TARGET], [x + Placement.NEXT_NAVIGATION_STEP, y, z]);
    }
    const pose = robot[PlannedRobotKey.POSE];
    const [x, y] = PlanPose.position(pose);
    const yaw = PlanPose.yaw(pose);
    return PlanPose.of(
      PlanPose.rounded(x + Placement.NAVIGATION_AHEAD * Math.cos(yaw)),
      PlanPose.rounded(y + Placement.NAVIGATION_AHEAD * Math.sin(yaw)),
      0,
      yaw,
    );
  }

  /**
   * Put a step's object down beside where it starts.
   * @param {Object} step A step that puts an object down.
   */
  #putDownBeside(step) {
    const placed = this.objects().find((item) => item[PlannedObjectKey.IDENTIFIER] === step[PlanStepKey.OBJECT]);
    step[PlanStepKey.PLACEMENT] ??= PlacementMode.POSE;
    if (!placed) return;
    const [x, y, z] = PlanPose.position(placed[PlannedObjectKey.POSE]);
    step[PlanStepKey.TARGET] = PlanPose.moved(placed[PlannedObjectKey.POSE], [x, y + Placement.PUT_DOWN_BESIDE, z]);
  }

  /**
   * @param {string} prefix The identity's prefix.
   * @param {Array<string>} taken The identities in use.
   * @returns {string} The prefix with the smallest number not in use.
   */
  #nextIdentity(prefix, taken) {
    let number = 1;
    while (taken.includes(`${prefix}${number}`)) number += 1;
    return `${prefix}${number}`;
  }

  /**
   * @param {Array} entries A list of the plan.
   * @param {string} limit The `PlanBuilderLimitsKey` bounding it.
   * @throws {PlanRefused} When the list holds as many entries as the limit allows.
   */
  #within(entries, limit) {
    const maximum = this.limits[limit];
    if (maximum !== undefined && entries.length >= maximum) throw new PlanRefused(`At most ${maximum} fit.`);
  }
}
